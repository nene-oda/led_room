"""`SceneRepository` sobre la `Session` sincrona de SQLModel.

Mismas reglas que los repositorios de dispositivos y de efectos: **sincrono a
proposito**, no traduce nada (eso vive en `mappers/scene.py`) y la sesion se
inyecta, no se crea aqui. Los metodos que hacen `commit()` se llaman desde el
threadpool.

Dos cosas propias de esta tabla:

* **`get_activation` hace UNA consulta con JOIN**, no una por objetivo: activar
  una escena es la ruta caliente de la Fase 6 y un `select` por objetivo es el
  N+1 clasico (NEXT_STEPS 6.7, paso 1).
* **Las claves foraneas se traducen a `ValueError`**. Un objetivo que apunta a un
  dispositivo o a un efecto inexistente es una peticion invalida del cliente
  (422), no un fallo del servidor; dejar subir el `IntegrityError` daria un 500
  generico y el cliente no sabria que corregir.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from backend.app.domain.scenes.models import Scene, SceneActivation
from backend.app.infrastructure.persistence.mappers.scene import (
    activation_to_domain,
    apply_scene_to_record,
    scene_to_domain,
    target_records,
)
from backend.app.infrastructure.persistence.models.effect import EffectRecord
from backend.app.infrastructure.persistence.models.scene import SceneRecord, SceneTargetRecord


class SQLModelSceneRepository:
    """Cumple el Protocol `backend.app.domain.scenes.repositories.SceneRepository`.

    No lo hereda: el puerto es estructural, y heredarlo ataria el dominio a que
    exista esta implementacion.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, scene_id: UUID) -> Scene | None:
        record = self._session.get(SceneRecord, scene_id)
        return None if record is None else scene_to_domain(record)

    def list_all(self) -> Sequence[Scene]:
        """Catalogo completo, en orden estable por nombre.

        Cada `scene_to_domain` carga sus objetivos de forma perezosa: son 1+N
        consultas contra un SQLite local con un puñado de filas, la misma
        decision (y el mismo motivo) que en el repositorio de efectos.
        """
        statement = select(SceneRecord).order_by(col(SceneRecord.name))
        return [scene_to_domain(record) for record in self._session.exec(statement).all()]

    def get_activation(self, scene_id: UUID) -> SceneActivation | None:
        """La escena con sus objetivos habilitados y los efectos ya resueltos.

        El orden por `device_id` hace la activacion reproducible: sin el, cual es
        el objetivo que se valida primero dependeria del orden de las filas.
        """
        record = self._session.get(SceneRecord, scene_id)
        if record is None:
            return None

        statement = (
            select(SceneTargetRecord, EffectRecord)
            .join(EffectRecord, col(SceneTargetRecord.effect_id) == col(EffectRecord.id))
            .where(col(SceneTargetRecord.scene_id) == scene_id)
            .where(col(SceneTargetRecord.enabled).is_(True))
            .order_by(col(SceneTargetRecord.device_id))
        )
        return activation_to_domain(record, self._session.exec(statement).all())

    def upsert(self, scene: Scene) -> Scene:
        """Crea o reemplaza por `id`. Devuelve la version persistida, que manda.

        La identidad es solo el `id`: dos escenas con el mismo nombre son
        legitimas (una copia que se esta editando, por ejemplo).
        """
        record = self._session.get(SceneRecord, scene.id)
        if record is None:
            # Solo la clave primaria: el resto lo escribe el mapper justo
            # despues, antes de cualquier flush.
            record = SceneRecord(id=scene.id)
            self._session.add(record)

        apply_scene_to_record(record, scene)

        # Los objetivos se reemplazan en dos tiempos, y el `flush` intermedio NO
        # es opcional: `scene_targets` tiene un UNIQUE (scene_id, device_id), asi
        # que si los INSERT de los nuevos salieran en el mismo flush que los
        # DELETE de los viejos, guardar dos veces la misma escena fallaria con un
        # IntegrityError. Es el mismo baile que con los pasos de un efecto.
        record.targets.clear()
        self._session.flush()
        record.targets.extend(target_records(record, scene))

        self._commit()
        self._session.refresh(record)
        return scene_to_domain(record)

    def delete(self, scene_id: UUID) -> bool:
        """`False` si no existia: el 404 lo decide el caso de uso, no el SQL.

        Los objetivos se van con el `ON DELETE CASCADE` de `scene_targets`, y los
        enlaces con perfiles con el de `profile_scenes`. Los efectos **no** se
        tocan: son catalogo compartido y otra escena puede estar usandolos.
        """
        record = self._session.get(SceneRecord, scene_id)
        if record is None:
            return False

        self._session.delete(record)
        self._session.commit()
        return True

    def _commit(self) -> None:
        """Confirma traduciendo la violacion de clave foranea a `ValueError` (422).

        El `rollback()` es imprescindible: sin el, la sesion queda en un estado
        invalido y la siguiente consulta de la MISMA peticion fallaria con un
        error sin relacion con la causa.
        """
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ValueError(
                "Algun objetivo de la escena apunta a un dispositivo o a un efecto "
                "que no existe: registra el dispositivo y guarda el efecto antes de "
                "referenciarlos."
            ) from error
