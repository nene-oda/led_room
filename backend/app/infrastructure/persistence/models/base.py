"""Piezas compartidas por los modelos persistentes.

Este modulo pertenece a INFRAESTRUCTURA. El dominio no lo importa nunca
(ARCHITECTURE 4, LED_ROOM_DATABASE_MODEL 53).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Dialect, TypeDecorator


def utc_now() -> datetime:
    """Instante actual con zona horaria explicita.

    `datetime.utcnow()` devuelve un naive que miente sobre su zona; nunca se usa.
    """
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """DATETIME que garantiza el viaje de ida y vuelta en UTC.

    SQLite no guarda el desplazamiento horario: con `DateTime(timezone=True)`
    de SQLAlchemy se escribe un datetime aware y se lee uno NAIVE, asi que
    comparar el valor leido con `utc_now()` revienta con
    "can't compare offset-naive and offset-aware datetimes". Verificado en
    SQLAlchemy 2.0.52.

    Aqui se normaliza a UTC al escribir y se vuelve a etiquetar al leer.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Se esperaba un datetime con zona horaria; use utc_now()")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)
