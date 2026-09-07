"""Codificacion de las tramas del controlador LotusLantern / ELK-BLEDOM.

**Todo lo que hay aqui esta verificado contra el hardware.** Cada trama de este
modulo se probo con `tools/ble/write_raw.py` sobre el controlador real y su
efecto lo confirmo una persona mirando la tira; la evidencia esta en
`docs/BLE_PROTOCOL.md` seccion 3. Lo que no se pudo verificar **no esta
implementado**, y esa ausencia es deliberada: `ARCHITECTURE.md` 8 prohibe
inventar UUIDs y bytes de comando, porque una trama adivinada no falla de
forma visible, se queda callada o deja el controlador en un modo del que no se
sabe salir.

El modulo es puro: no importa Bleak ni abre ningun enlace. Se puede probar
entero sin radio, y el adaptador que escribe en el enlace es otro (regla de
mantener la codificacion del protocolo centralizada y fuera de los servicios).
"""

from __future__ import annotations

from typing import Final

from backend.app.domain.lighting import BRIGHTNESS_MAX, BRIGHTNESS_MIN

#: Servicio propietario del controlador. El otro que expone es `00001800`
#: (Generic Access), estandar del perfil Bluetooth: nunca lleva protocolo de
#: fabricante.
CONTROL_SERVICE_UUID: Final = "0000fff0-0000-1000-8000-00805f9b34fb"

#: Caracteristica por la que se envian los comandos. Sus `properties` son
#: `read, write-without-response`: **no admite escritura con respuesta**, asi
#: que quien escriba debe pasar `response=False`. Pedir confirmacion a una
#: caracteristica que no la ofrece falla.
WRITE_CHARACTERISTIC_UUID: Final = "0000fff3-0000-1000-8000-00805f9b34fb"

#: Caracteristica de notificacion del controlador. Existe (handle 6, `notify`),
#: pero **todavia no se ha comprobado si emite algo**. Hasta saberlo, el estado
#: del hardware no es legible y hay que seguir tratandolo como divergente del
#: estado deseado.
NOTIFY_CHARACTERISTIC_UUID: Final = "0000fff4-0000-1000-8000-00805f9b34fb"

#: Longitud fija observada en todas las tramas que funcionaron.
FRAME_LENGTH: Final = 9

_HEADER: Final = 0x7E
_TERMINATOR: Final = 0xEF

#: Byte de comando, en el indice 2 de la trama.
_CMD_BRIGHTNESS: Final = 0x01
_CMD_COLOR: Final = 0x05
_CMD_POWER: Final = 0x04

#: Indice 3 del comando de encendido: es el byte que decide. Verificado en
#: las dos direcciones sobre el hardware.
_POWER_ON: Final = 0xF0
_POWER_OFF: Final = 0x00

#: Sub-modo del comando de color, en el indice 3. Verificado solo para color
#: estatico RGB; los modos preprogramados del controlador usan otros valores
#: que no se han explorado.
_MODE_STATIC_RGB: Final = 0x03


def _frame(*payload: int) -> bytes:
    """Envuelve `payload` entre la cabecera y el cierre, y valida la longitud.

    Centralizar el sobre evita que cada comando repita `7e ... ef` y que un
    error de longitud llegue al hardware: una trama corta no da error, el
    controlador simplemente la ignora, y eso se depura muy mal.
    """
    frame = bytes((_HEADER, 0x00, *payload, _TERMINATOR))
    if len(frame) != FRAME_LENGTH:
        message = f"Trama de {len(frame)} bytes; el controlador espera {FRAME_LENGTH}"
        raise ValueError(message)
    return frame


def encode_color(red: int, green: int, blue: int) -> bytes:
    """Color estatico. Los tres canales van en 0-255.

    Verificado: `ff 00 00` puso la tira roja y `00 ff 00` la puso verde, lo que
    demuestra que el orden es **RGB** y no RBG (el rojo solo no lo distingue,
    porque sale igual en ambos ordenes).
    """
    for name, value in (("red", red), ("green", green), ("blue", blue)):
        if not 0 <= value <= 255:
            message = f"El canal {name} vale {value}; debe estar entre 0 y 255"
            raise ValueError(message)
    return _frame(_CMD_COLOR, _MODE_STATIC_RGB, red, green, blue, 0x00)


def encode_brightness(brightness: int) -> bytes:
    """Brillo como porcentaje 0-100.

    Verificado: `0x0a` (10) atenuo la tira y `0x64` (100) la ilumino. **La
    escala del hardware coincide con la del dominio**, asi que no hay
    reescalado y no hay ningun sitio donde equivocarse con un factor.
    """
    if not BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX:
        message = (
            f"El brillo vale {brightness}; debe estar entre {BRIGHTNESS_MIN} y {BRIGHTNESS_MAX}"
        )
        raise ValueError(message)
    return _frame(_CMD_BRIGHTNESS, brightness, 0x00, 0x00, 0x00, 0x00)


def encode_power(on: bool) -> bytes:
    """Enciende o apaga la tira.

    Verificado en las dos direcciones, que es lo que hace concluyente la prueba:
    `7e 00 04 00 ...` apago la tira, y despues `7e 00 04 f0 ...` la volvio a
    encender. La primera candidata que se probo (`7e 00 04 f0 00 00 ff 00 ef`)
    no hizo nada, asi que el byte que manda es el del indice 3: `0x00` apaga,
    `0xf0` enciende.

    **Se envian los bytes exactos que se observaron funcionando**, incluidas las
    diferencias de los indices 5 y 6 entre una trama y otra. Podrian ser
    irrelevantes -- y unificarlas quedaria mas limpio --, pero eso no se ha
    comprobado, y una trama "ordenada" que el controlador ignore en silencio es
    justo el fallo que no se detecta hasta tener la tira delante.

    Encender **no** restablece nada: el controlador guarda color y brillo, y
    vuelve con los que tenia. El adaptador no debe reenviarlos.
    """
    if on:
        return _frame(_CMD_POWER, _POWER_ON, 0x00, 0x00, 0x00, 0x00)
    return _frame(_CMD_POWER, _POWER_OFF, 0x00, 0x00, 0xFF, 0x00)
