"""Puerto de persistencia de dispositivos (NEXT_STEPS A3).

**Correccion explicita a `LED_ROOM_DATABASE_MODEL.md` 50**, que define este
repositorio devolviendo el `Device` de SQLModel. Eso mete SQLModel en la firma
que consume la capa de aplicacion y anula la separacion que el propio 53 exige:
un servicio tipado contra `DeviceRecord` no se puede probar sin base de datos ni
migrar a otro almacenamiento. Aqui las firmas hablan tipos de DOMINIO (`Device`,
`LightState`, `UUID`) y la traduccion vive en
`infrastructure/persistence/mappers/`.

Los metodos son **sincronos a proposito**: la implementacion usa la `Session`
sincrona de SQLModel y hacerlos `async` contagiaria ese `async` a toda la capa
de aplicacion sin ganar nada (NEXT_STEPS 4.5).

Ser sincronos es justamente lo que obliga a **llamarlos desde el threadpool**
(`run_in_threadpool` en la frontera HTTP): invocarlos desde una corrutina los
ejecuta en el bucle de eventos, y una espera de SQLite ahi congela las escrituras
BLE, la difusion y `/health`.

Protocolo estrecho: solo lo que las Fases 1-4 necesitan. Nada de un
`CrudRepository[T]` generico, y ningun repositorio para tablas sin caso de uso
propietario (ARCHITECTURE 7.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from backend.app.domain.devices.models import Device
from backend.app.domain.lighting import LightState


@runtime_checkable
class DeviceRepository(Protocol):
    """Lectura y escritura de la identidad de dispositivos y su estado deseado."""

    def get(self, device_id: UUID) -> Device | None: ...

    def get_by_address(self, address: str) -> Device | None:
        """Resuelve un resultado de escaneo contra lo ya registrado."""
        ...

    def list_enabled(self) -> Sequence[Device]:
        """Dispositivos utilizables. Un dispositivo deshabilitado no se conecta."""
        ...

    def upsert(self, device: Device) -> Device:
        """Crea o actualiza por `id`. Devuelve la version persistida."""
        ...

    def load_state(self, device_id: UUID) -> LightState | None:
        """Ultimo estado deseado. `None` si nunca se guardo ninguno."""
        ...

    def save_state(self, device_id: UUID, state: LightState) -> None:
        """Persiste el estado deseado.

        Se llama ante **intencion del usuario**, jamas por fotograma: durante un
        efecto o un arrastre del selector de color no se escribe nada
        (NEXT_STEPS A3).
        """
        ...
