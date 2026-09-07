"""`EffectRepository` sobre la `Session` sincrona de SQLModel.

Mismas reglas que el repositorio de dispositivos: **sincrono a proposito**, no
traduce nada (eso vive en `mappers/effect.py`) y la sesion se inyecta, no se
crea aqui.

Los metodos que hacen `commit()` pueden esperar hasta `busy_timeout`, asi que se
llaman desde el threadpool. Los que solo leen por clave primaria los puede usar
la capa de aplicacion directamente, igual que hace `DeviceService.connect`.

Lo unico que si se traduce aqui es la **violacion de clave foranea**, igual que
en escenas y perfiles: es un `IntegrityError` de SQLAlchemy, y la capa de
aplicacion no puede importarlo (lo prohibe su guardian de fronteras). Sube ya
convertido en la excepcion que la politica de errores sabe mapear.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backend.app.application.errors import EffectInUseError
from backend.app.domain.effects.models import EffectDefinition
from backend.app.infrastructure.persistence.mappers.effect import (
    apply_effect_to_record,
    effect_to_domain,
    step_records,
)
from backend.app.infrastructure.persistence.models.effect import EffectRecord


class SQLModelEffectRepository:
    """Cumple el Protocol `backend.app.domain.effects.repositories.EffectRepository`.

    No lo hereda: el puerto es estructural, y heredarlo ataria el dominio a que
    exista esta implementacion.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, effect_id: UUID) -> EffectDefinition | None:
        record = self._session.get(EffectRecord, effect_id)
        return None if record is None else effect_to_domain(record)

    def list_all(self) -> Sequence[EffectDefinition]:
        """Catalogo completo, en orden estable por nombre.

        Cada `effect_to_domain` carga sus pasos de forma perezosa: son 1+N
        consultas contra un SQLite local con un puñado de filas. Precargar con
        `selectinload` exigiria hoy un `type: ignore`, porque SQLModel tipa la
        relacion como el modelo destino y no como `QueryableAttribute`.
        """
        statement = select(EffectRecord).order_by(col(EffectRecord.name))
        return [effect_to_domain(record) for record in self._session.exec(statement).all()]

    def upsert(self, effect: EffectDefinition) -> EffectDefinition:
        """Crea o reemplaza por `id`. Devuelve la version persistida, que manda.

        La identidad es solo el `id`: a diferencia de los dispositivos, un efecto
        no tiene una identidad fisica alternativa, y dos efectos con el mismo
        nombre son legitimos (una copia que se esta editando, por ejemplo).
        """
        record = self._session.get(EffectRecord, effect.id)
        if record is None:
            # Solo la clave primaria: el resto lo escribe el mapper justo
            # despues, antes de cualquier flush.
            record = EffectRecord(id=effect.id)
            self._session.add(record)

        apply_effect_to_record(record, effect)

        # Los pasos se reemplazan en dos tiempos, y el `flush` intermedio NO es
        # opcional: `effect_steps` tiene un UNIQUE (effect_id, position), asi
        # que si los INSERT de los pasos nuevos salieran en el mismo flush que
        # los DELETE de los viejos, guardar dos veces el mismo efecto fallaria
        # con un IntegrityError. Vaciar, vaciar de verdad, y luego insertar.
        record.steps.clear()
        self._session.flush()
        record.steps.extend(step_records(record, effect))

        self._session.commit()
        self._session.refresh(record)
        return effect_to_domain(record)

    def delete(self, effect_id: UUID) -> bool:
        """`False` si no existia: el 404 lo decide el caso de uso, no el SQL.

        Los pasos se van con el `ON DELETE CASCADE` de `effect_steps`. Lo que no
        se va son los `scene_targets`, que apuntan al efecto con `RESTRICT`:
        borrar un efecto que alguna escena usa falla en la base, que es
        exactamente lo que se quiere.

        Ese fallo se traduce **aqui**, y no en la capa de aplicacion, por la
        misma razon que en escenas y perfiles: el `IntegrityError` es de
        SQLAlchemy y la capa de aplicacion no puede importarlo. Dejarlo subir
        crudo lo convertia en un `500 internal_error` -- un fallo del servidor
        por lo que en realidad es un error del usuario, y con un mensaje generico
        que no le decia que hacer.
        """
        record = self._session.get(EffectRecord, effect_id)
        if record is None:
            return False

        self._session.delete(record)
        try:
            self._session.commit()
        except IntegrityError as error:
            # El `rollback()` es imprescindible: sin el, la sesion queda en un
            # estado invalido y la siguiente consulta de la MISMA peticion
            # fallaria con un error sin relacion con la causa.
            self._session.rollback()
            raise EffectInUseError(
                f"Alguna escena usa el efecto {effect_id}: quita ese objetivo de la "
                "escena (o borra la escena) antes de borrar el efecto."
            ) from error
        return True
