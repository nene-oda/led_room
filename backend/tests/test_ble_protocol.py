"""Las tramas que se envian al controlador real, byte a byte.

Estas pruebas fijan **evidencia de hardware**, no una decision de diseño: cada
trama esperada aqui se probo con `tools/ble/write_raw.py` sobre el controlador
y su efecto lo confirmo una persona mirando la tira. Si una falla, o alguien
cambio la codificacion, o el hardware no es el que creemos: en ninguno de los
dos casos vale con actualizar el valor esperado sin volver a probarlo.
"""

from __future__ import annotations

import pytest

from backend.app.infrastructure.bluetooth import protocol


def test_el_color_es_la_trama_verificada_contra_la_tira() -> None:
    """`ff 00 00` es la trama que puso la tira roja."""
    assert protocol.encode_color(255, 0, 0) == bytes.fromhex("7e000503ff000000ef")


def test_el_orden_de_canales_es_rgb_no_rbg() -> None:
    """El rojo solo no lo demuestra: sale igual en RGB y en RBG.

    Lo decide el verde, que se probo y salio verde.
    """
    verde = protocol.encode_color(0, 255, 0)

    assert verde == bytes.fromhex("7e00050300ff0000ef")
    # El byte del medio de los tres es el verde, no el azul.
    assert verde[4:7] == bytes((0, 255, 0))


def test_el_brillo_es_la_trama_verificada_contra_la_tira() -> None:
    """`0x0a` atenuo y `0x64` ilumino."""
    assert protocol.encode_brightness(10) == bytes.fromhex("7e00010a00000000ef")
    assert protocol.encode_brightness(100) == bytes.fromhex("7e00016400000000ef")


def test_el_brillo_no_se_reescala() -> None:
    """El hardware usa 0-100, igual que el dominio: el valor viaja intacto.

    Si algun dia alguien mete un factor 255/100, este test lo caza.
    """
    for nivel in (0, 1, 37, 99, 100):
        assert protocol.encode_brightness(nivel)[3] == nivel


@pytest.mark.parametrize(
    "trama",
    [
        protocol.encode_color(1, 2, 3),
        protocol.encode_brightness(50),
    ],
)
def test_toda_trama_lleva_el_sobre_y_la_longitud_del_controlador(trama: bytes) -> None:
    assert len(trama) == protocol.FRAME_LENGTH
    assert trama[0] == 0x7E
    assert trama[-1] == 0xEF


@pytest.mark.parametrize(
    ("red", "green", "blue"),
    [(256, 0, 0), (0, 256, 0), (0, 0, 256), (-1, 0, 0)],
)
def test_un_canal_fuera_de_rango_no_llega_al_hardware(red: int, green: int, blue: int) -> None:
    """Se corta aqui, no en el enlace: `bytes()` lanzaria un error opaco."""
    with pytest.raises(ValueError, match="entre 0 y 255"):
        protocol.encode_color(red, green, blue)


@pytest.mark.parametrize("brillo", [-1, 101, 255])
def test_un_brillo_fuera_del_porcentaje_no_llega_al_hardware(brillo: int) -> None:
    with pytest.raises(ValueError, match="entre 0 y 100"):
        protocol.encode_brightness(brillo)


def test_el_encendido_y_el_apagado_son_las_tramas_verificadas() -> None:
    """Las dos direcciones se probaron: apago, y despues encendio.

    Se comparan los bytes EXACTOS que funcionaron. Los indices 5 y 6 difieren
    entre encender y apagar; podrian ser irrelevantes, pero eso no se comprobo,
    y "ordenar" la trama sin evidencia es exactamente como se acaba enviando
    algo que el controlador ignora en silencio.
    """
    assert protocol.encode_power(False) == bytes.fromhex("7e0004000000ff00ef")
    assert protocol.encode_power(True) == bytes.fromhex("7e0004f000000000ef")


def test_el_byte_que_decide_el_encendido_es_el_indice_3() -> None:
    """La primera candidata fallida solo se diferenciaba en otros bytes.

    `7e 00 04 f0 00 00 ff 00 ef` no hizo nada pese a llevar `f0`, asi que el
    valor por si solo no basta; lo que quedo demostrado es el par completo.
    """
    assert protocol.encode_power(True)[3] == 0xF0
    assert protocol.encode_power(False)[3] == 0x00


def test_encender_no_reenvia_color_ni_brillo() -> None:
    """El controlador conserva su estado: al encender vuelve como estaba.

    Observado sobre el hardware. Si alguien mete aqui el color, el encendido
    pisaria lo que el usuario tenia puesto.
    """
    trama = protocol.encode_power(True)

    assert trama[4:8] == bytes(4)
