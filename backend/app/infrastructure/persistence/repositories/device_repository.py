"""`DeviceRepository` sobre la `Session` sincrona de SQLModel.

**Sincrono a proposito**: convertirlo a `AsyncSession` no aportaria nada hoy y
contagiaria `async` a toda la capa de aplicacion (LED_ROOM_DATABASE_MODEL 52,
NEXT_STEPS 4.5).

Ser sincrono NO lo saca por si solo del bucle de eventos. Lo que FastAPI ejecuta
en el threadpool es la *dependencia* que abre y cierra la `Session`, no estos
metodos, que los llama una ruta `async`. Sacarlos del bucle es responsabilidad de
quien llama, y por eso las rutas los envuelven en `run_in_threadpool`: con
`PRAGMA busy_timeout=5000`, un `commit()` que espere a otro escritor congelaria
el bucle entero hasta 5 s.

Esta clase no traduce nada: toda la conversion dominio <-> columnas vive en
`persistence/mappers/device.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlmodel import Session, col, select

from backend.app.domain.devices.models import Device
from backend.app.domain.lighting import LightState
from backend.app.infrastructure.persistence.mappers.device import (
    adapter_type_to_column,
    apply_device_to_record,
    apply_state_to_record,
    device_to_domain,
    state_to_domain,
)
from backend.app.infrastructure.persistence.models.device import DeviceRecord, DeviceStateRecord


class SQLModelDeviceRepository:
    """Cumple el Protocol `backend.app.domain.devices.repositories.DeviceRepository`.

    No lo hereda: el puerto es estructural, y heredarlo ataria el dominio a que
    exista esta implementacion.

    La sesion se inyecta; el repositorio no la crea ni la cierra. Quien la abre
    (la dependencia de FastAPI o `session_scope`) es quien decide su alcance.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, device_id: UUID) -> Device | None:
        record = self._session.get(DeviceRecord, device_id)
        return None if record is None else device_to_domain(record)

    def get_by_address(self, address: str) -> Device | None:
        """Resuelve un resultado de escaneo contra lo ya registrado.

        La direccion no es portable entre hosts (MAC en Linux, GUID de WinRT en
        Windows): siempre viene de un escaneo real, nunca escrita en el codigo.
        """
        statement = select(DeviceRecord).where(col(DeviceRecord.ble_address) == address)
        record = self._session.exec(statement).first()
        return None if record is None else device_to_domain(record)

    def list_enabled(self) -> Sequence[Device]:
        """Dispositivos utilizables, en orden estable por nombre.

        Cada `device_to_domain` carga su fila 1:1 de capacidades de forma
        perezosa, asi que son 1+N consultas contra un SQLite local con un puñado
        de filas. Precargar con `selectinload` exigiria hoy un `type: ignore`
        porque SQLModel tipa la relacion como el modelo destino y no como
        `QueryableAttribute`; no compensa mientras N sea el numero de tiras de
        LED de una habitacion.
        """
        statement = (
            select(DeviceRecord)
            .where(col(DeviceRecord.enabled).is_(True))
            .order_by(col(DeviceRecord.name))
        )
        return [device_to_domain(record) for record in self._session.exec(statement).all()]

    def upsert(self, device: Device) -> Device:
        """Crea o actualiza. Devuelve la version persistida, que manda.

        Identidad, en este orden:

        1. por `id`, que es la identidad autoritativa;
        2. si no existe y hay direccion, por `(adapter_type, ble_address)`, para
           no registrar dos veces el mismo controlador fisico descubierto en dos
           escaneos distintos.

        Cuando gana el paso 2, el `id` devuelto es el de la fila existente y NO
        el del argumento: reescribir la clave primaria dejaria huerfanas las
        filas hijas. Por eso se devuelve el dispositivo releido y no el recibido.
        """
        record = self._session.get(DeviceRecord, device.id)
        if record is None:
            record = self._find_by_transport_identity(device)
        if record is None:
            # Solo la clave primaria: el resto de columnas las escribe el
            # mapper justo despues, antes de cualquier flush.
            record = DeviceRecord(id=device.id)
            self._session.add(record)

        apply_device_to_record(record, device)
        self._session.commit()
        self._session.refresh(record)
        return device_to_domain(record)

    def load_state(self, device_id: UUID) -> LightState | None:
        record = self._session.get(DeviceStateRecord, device_id)
        return None if record is None else state_to_domain(record)

    def save_state(self, device_id: UUID, state: LightState) -> None:
        """Persiste el estado deseado ante intencion del usuario.

        Jamas por fotograma: durante un efecto o un arrastre del selector de
        color no se escribe nada (NEXT_STEPS A3). Lo efimero (conectado, RSSI)
        no tiene columna y no se persiste.

        Hace `commit()`, asi que puede esperar hasta `busy_timeout`: llamalo
        desde el threadpool, nunca directamente desde una corrutina.
        """
        record = self._session.get(DeviceStateRecord, device_id)
        if record is None:
            record = DeviceStateRecord(device_id=device_id)
            self._session.add(record)

        apply_state_to_record(record, state)
        self._session.commit()

    def _find_by_transport_identity(self, device: Device) -> DeviceRecord | None:
        if device.address is None:
            return None

        statement = select(DeviceRecord).where(
            col(DeviceRecord.adapter_type) == adapter_type_to_column(device.adapter_type),
            col(DeviceRecord.ble_address) == device.address,
        )
        return self._session.exec(statement).first()
