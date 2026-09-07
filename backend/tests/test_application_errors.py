"""La politica de errores (NEXT_STEPS A6), antes de que exista ningun handler.

Se prueba aqui, en la capa de aplicacion, porque la traduccion debe ser la misma
para REST y para el frame `error` del WebSocket. Si cada transporte decidiera su
codigo, el mismo fallo tendria dos significados.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.application.errors import (
    INTERNAL_MESSAGE,
    DeviceBusyError,
    DeviceNotFoundError,
    EffectInUseError,
    ErrorCode,
    translate_error,
)
from backend.app.domain.devices.ports import (
    DeviceCapabilityError,
    DeviceError,
    DeviceNotConnectedError,
    DeviceUnavailableError,
)
from backend.app.domain.lighting import LightState
from backend.app.infrastructure.persistence.mappers.device import DeviceMappingError


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (DeviceNotFoundError("no existe"), 404, ErrorCode.DEVICE_NOT_FOUND),
        (DeviceBusyError("otro enlace"), 409, ErrorCode.DEVICE_BUSY),
        # 409 y no 422: la peticion es valida, lo que lo impide es el catalogo.
        (EffectInUseError("lo usa una escena"), 409, ErrorCode.EFFECT_IN_USE),
        (DeviceNotConnectedError("sin enlace"), 409, ErrorCode.DEVICE_NOT_CONNECTED),
        (DeviceCapabilityError("sin brillo"), 409, ErrorCode.UNSUPPORTED_CAPABILITY),
        # 503 y no 502: el fallo no esta en el dispositivo sino en el host, y
        # lo que hay que arreglar (encender el Bluetooth) esta al alcance de
        # quien lo pidio. Va antes que `DeviceError` en la tabla porque hereda
        # de el; sin ese orden, este caso saldria como 502.
        (DeviceUnavailableError("bluetooth apagado"), 503, ErrorCode.DEVICE_UNAVAILABLE),
        (DeviceError("escritura fallida"), 502, ErrorCode.DEVICE_WRITE_FAILED),
        (ValueError("brillo fuera de rango"), 422, ErrorCode.INVALID_PAYLOAD),
    ],
)
def test_cada_fallo_conocido_tiene_su_codigo(
    error: Exception, status_code: int, code: ErrorCode
) -> None:
    translation = translate_error(error)

    assert translation.status_code == status_code
    assert translation.code is code
    assert translation.message == str(error)


def test_las_subclases_ganan_a_la_base_device_error() -> None:
    """`DeviceNotConnectedError` es un `DeviceError`: 409, no 502."""
    assert isinstance(DeviceNotConnectedError("x"), DeviceError)
    assert translate_error(DeviceNotConnectedError("x")).status_code == 409


def test_una_escritura_colgada_llega_como_error_de_dispositivo_no_como_timeout() -> None:
    """`SerializedLightDevice` ya traduce el timeout: aqui es un 502, no un 500."""
    timeout = TimeoutError("write_gatt_char colgado")

    assert translate_error(timeout).status_code == 500
    assert translate_error(DeviceError(str(timeout))).status_code == 502


def test_un_rango_invalido_de_pydantic_es_un_422() -> None:
    """`ValidationError` hereda de `ValueError`: no hace falta un caso aparte."""
    with pytest.raises(ValidationError) as raised:
        LightState(brightness=101)

    assert translate_error(raised.value).code is ErrorCode.INVALID_PAYLOAD


def test_una_fila_corrupta_es_un_500_y_no_filtra_su_mensaje() -> None:
    """`DeviceMappingError` no hereda de `ValueError` justamente para caer aqui.

    Cae en el caso por defecto sin que la capa de aplicacion tenga que importar
    infraestructura: una fila escrita a mano es un fallo del servidor, no una
    peticion invalida del cliente.
    """
    translation = translate_error(DeviceMappingError("adapter_type desconocido: 'wled'"))

    assert translation.status_code == 500
    assert translation.code is ErrorCode.INTERNAL_ERROR
    assert translation.message == INTERNAL_MESSAGE
    assert "wled" not in translation.message


def test_un_fallo_inesperado_no_devuelve_nada_del_interior() -> None:
    translation = translate_error(RuntimeError("/ruta/interna/secreta"))

    assert translation.status_code == 500
    assert translation.message == INTERNAL_MESSAGE
