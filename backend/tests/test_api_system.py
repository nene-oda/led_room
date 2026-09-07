"""`GET /api/v1/system`: que puede hacer este servidor, antes de pedirselo.

El fallo de producto que motiva estos tests: con el adaptador sin hardware,
`GET /devices/scan` responde `200 []` al instante y el cliente no puede
distinguir "no habia nada cerca" de "este servidor no tiene radio".
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.domain.devices.models import DeviceType
from backend.app.infrastructure.devices import registry
from backend.app.main import create_app
from backend.tests.doubles import api_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return api_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


def _system(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/v1/system")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_el_adaptador_sin_hardware_declara_que_no_puede_descubrir(client: TestClient) -> None:
    """Contrato exacto: con estas cuatro claves el cliente decide si ofrece el boton."""
    assert _system(client) == {
        "adapter_type": "null",
        "discovery_type": "null",
        "supports_discovery": False,
        "scan_timeout_seconds": 10.0,
    }


def test_la_capacidad_sale_de_la_declaracion_y_no_del_nombre_del_adaptador(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un adaptador simulado CON radio: mismo `adapter_type`, otra capacidad.

    Es la regresion que impide volver a un `if adapter_type == "null"` disperso:
    aqui el tipo sigue siendo `null` y la respuesta debe decir `true` porque lo
    dice su `AdapterRegistration`.
    """
    con_radio = dataclasses.replace(registry.ADAPTERS[DeviceType.NULL], supports_discovery=True)
    monkeypatch.setattr(registry, "ADAPTERS", {**registry.ADAPTERS, DeviceType.NULL: con_radio})

    with TestClient(create_app(settings)) as client:
        assert _system(client) == {
            "adapter_type": "null",
            "discovery_type": "null",
            "supports_discovery": True,
            "scan_timeout_seconds": 10.0,
        }


def test_descubrir_y_controlar_se_publican_por_separado(tmp_path: Path) -> None:
    """La configuracion de hoy: control sin hardware y busqueda BLE real.

    Es el motivo de que `discovery_type` exista. Con un solo campo, un
    `supports_discovery: true` junto a `adapter_type: "null"` parecia una
    contradiccion y no habia forma de saber que escaner iba a responder.
    """
    settings = api_settings(tmp_path).model_copy(
        update={"device_discovery": DeviceType.LOTUS_LANTERN}
    )

    with TestClient(create_app(settings)) as client:
        assert _system(client) == {
            "adapter_type": "null",
            "discovery_type": "lotus_lantern",
            "supports_discovery": True,
            "scan_timeout_seconds": 10.0,
        }


def test_el_tiempo_de_escaneo_publicado_es_el_configurado(tmp_path: Path) -> None:
    """Es la cota superior de `GET /devices/scan`, no un valor decorativo.

    En punto flotante a proposito: redondear mentiria sobre un timeout de 2,5 s.
    """
    settings = api_settings(tmp_path).model_copy(update={"ble_scan_timeout": 2.5})

    with TestClient(create_app(settings)) as client:
        assert _system(client)["scan_timeout_seconds"] == 2.5


def test_el_estado_global_no_repite_la_configuracion_del_servidor(client: TestClient) -> None:
    """`/state` describe la habitacion y se difunde en cada cambio; esto no cabe ahi."""
    state = client.get("/api/v1/state").json()

    assert set(state) == {"version", "device", "light", "effect", "scene"}


def test_el_escaneo_sin_radio_sigue_respondiendo_200_con_lista_vacia(client: TestClient) -> None:
    """El contrato de `/devices/scan` NO cambia: un escaneo vacio no es un error.

    Quien decide no ofrecer el boton es el cliente, con `/system`. Devolver 409 o
    503 obligaria a tratar como fallo lo que es una respuesta correcta, y romperia
    a cualquier cliente ya escrito.
    """
    response = client.get("/api/v1/devices/scan?timeout=1")

    assert response.status_code == 200
    assert response.json() == []
