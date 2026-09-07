"""La persistencia de escenas y perfiles tampoco puede correr EN el bucle.

Extiende el guardian de `test_blocking_boundary.py` a las rutas de las Fases 6 y
7. Vive en un modulo aparte porque monta otros dobles, pero la regla es la misma
y el motivo tambien: las rutas son `async`, asi que una consulta sin
`run_in_threadpool` corre en el bucle de eventos y, con
`PRAGMA busy_timeout=5000`, un escritor concurrente lo congela hasta 5 s -- sin
escrituras BLE, sin difusion y sin `/health`.

Las dos excepciones son las lecturas de las dos activaciones (`get_activation` en
escenas y `get` en perfiles), y son deliberadas: las hacen `SceneService.activate`
y `ProfileService.activate`, que son corrutinas, desde DENTRO del bucle. Sacarlas
de ahi exigiria que la capa de aplicacion importara Starlette, y eso invierte la
direccion de las dependencias (lo vigila `test_application_boundaries.py`). Se
aceptan porque son lecturas acotadas por clave primaria -- una con un JOIN -- y no
`commit()`, que es lo que puede quedarse esperando a `busy_timeout`. Es la misma
excepcion que ya tiene el `get` de `DeviceService.connect`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import deps
from backend.app.config import Settings
from backend.app.domain.effects.models import EffectDefinition, EffectStep, EffectType
from backend.app.domain.lighting import RGBColor
from backend.app.domain.profiles.models import Profile
from backend.app.domain.profiles.repositories import ProfileRepository
from backend.app.domain.scenes.models import Scene, SceneActivation
from backend.app.domain.scenes.repositories import SceneRepository
from backend.app.main import create_app
from backend.tests.doubles import (
    InMemoryProfileRepository,
    InMemorySceneRepository,
    api_settings,
)

ADDRESS = "BE:FF:00:11:22:33"

EFECTO = EffectDefinition(
    id=uuid4(),
    name="Morado fijo",
    type=EffectType.STATIC,
    steps=(EffectStep(position=0, color=RGBColor.from_hex("#7B00FF")),),
)


def _in_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class LoopAwareSceneRepository(InMemorySceneRepository):
    """Anota, por metodo, si se le llamo desde dentro del bucle de eventos."""

    calls: ClassVar[dict[str, list[bool]]] = {}

    def _note(self, name: str) -> None:
        LoopAwareSceneRepository.calls.setdefault(name, []).append(_in_event_loop())

    def get(self, scene_id: UUID) -> Scene | None:
        self._note("get")
        return super().get(scene_id)

    def list_all(self) -> Sequence[Scene]:
        self._note("list_all")
        return super().list_all()

    def get_activation(self, scene_id: UUID) -> SceneActivation | None:
        self._note("get_activation")
        return super().get_activation(scene_id)

    def upsert(self, scene: Scene) -> Scene:
        self._note("upsert")
        return super().upsert(scene)

    def delete(self, scene_id: UUID) -> bool:
        self._note("delete")
        return super().delete(scene_id)


class LoopAwareProfileRepository(InMemoryProfileRepository):
    calls: ClassVar[dict[str, list[bool]]] = {}

    def _note(self, name: str) -> None:
        LoopAwareProfileRepository.calls.setdefault(name, []).append(_in_event_loop())

    def get(self, profile_id: UUID) -> Profile | None:
        self._note("get")
        return super().get(profile_id)

    def list_all(self) -> Sequence[Profile]:
        self._note("list_all")
        return super().list_all()

    def upsert(self, profile: Profile) -> Profile:
        self._note("upsert")
        return super().upsert(profile)

    def delete(self, profile_id: UUID) -> bool:
        self._note("delete")
        return super().delete(profile_id)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return api_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    LoopAwareSceneRepository.calls = {}
    LoopAwareProfileRepository.calls = {}
    scenes = LoopAwareSceneRepository(effects=[EFECTO])
    profiles = LoopAwareProfileRepository()

    def scene_factory() -> SceneRepository:
        return scenes

    def profile_factory() -> ProfileRepository:
        return profiles

    app: FastAPI = create_app(settings)
    app.dependency_overrides[deps.get_scene_repository] = scene_factory
    app.dependency_overrides[deps.get_profile_repository] = profile_factory
    with TestClient(app) as client:
        yield client


def _dispositivo_conectado(client: TestClient) -> str:
    created: dict[str, Any] = client.post(
        "/api/v1/devices", json={"name": "Tira", "address": ADDRESS}
    ).json()
    assert client.post(f"/api/v1/devices/{created['id']}/connect").status_code == 200
    identifier: str = created["id"]
    return identifier


def test_las_rutas_de_escenas_no_consultan_la_base_desde_el_bucle(client: TestClient) -> None:
    device_id = _dispositivo_conectado(client)
    creada: dict[str, Any] = client.post(
        "/api/v1/scenes",
        json={
            "name": "Noche",
            "targets": [{"device_id": device_id, "effect_id": str(EFECTO.id)}],
        },
    ).json()

    assert client.get("/api/v1/scenes").status_code == 200
    assert client.get(f"/api/v1/scenes/{creada['id']}").status_code == 200
    assert client.post(f"/api/v1/scenes/{creada['id']}/duplicate").status_code == 201
    assert client.post(f"/api/v1/scenes/{creada['id']}/activate").status_code == 200
    assert client.delete(f"/api/v1/scenes/{creada['id']}").status_code == 204

    for name in ("get", "list_all", "upsert", "delete"):
        llamadas = LoopAwareSceneRepository.calls.get(name, [])
        assert llamadas, f"{name} no llego a llamarse: el test no probaria nada"
        assert not any(llamadas), (
            f"{name} corrio en el bucle de eventos: envuelvelo en `run_in_threadpool`"
        )


def test_la_activacion_lee_desde_el_bucle_a_proposito(client: TestClient) -> None:
    """Excepcion documentada, igual que el `get` de `DeviceService.connect`."""
    device_id = _dispositivo_conectado(client)
    creada: dict[str, Any] = client.post(
        "/api/v1/scenes",
        json={
            "name": "Noche",
            "targets": [{"device_id": device_id, "effect_id": str(EFECTO.id)}],
        },
    ).json()

    client.post(f"/api/v1/scenes/{creada['id']}/activate")

    assert LoopAwareSceneRepository.calls["get_activation"] == [True]


def test_las_rutas_de_perfiles_no_consultan_la_base_desde_el_bucle(client: TestClient) -> None:
    device_id = _dispositivo_conectado(client)
    escena: dict[str, Any] = client.post(
        "/api/v1/scenes",
        json={
            "name": "Noche",
            "targets": [{"device_id": device_id, "effect_id": str(EFECTO.id)}],
        },
    ).json()
    creado: dict[str, Any] = client.post(
        "/api/v1/profiles",
        json={"name": "Sleep", "scenes": [{"scene_id": escena["id"]}]},
    ).json()

    assert client.get("/api/v1/profiles").status_code == 200
    assert client.get(f"/api/v1/profiles/{creado['id']}").status_code == 200
    assert client.delete(f"/api/v1/profiles/{creado['id']}").status_code == 204

    for name in ("get", "list_all", "upsert", "delete"):
        llamadas = LoopAwareProfileRepository.calls.get(name, [])
        assert llamadas, f"{name} no llego a llamarse: el test no probaria nada"
        assert not any(llamadas), (
            f"{name} corrio en el bucle de eventos: envuelvelo en `run_in_threadpool`"
        )


def test_activar_un_perfil_tambien_lee_desde_el_bucle_a_proposito(client: TestClient) -> None:
    """Misma excepcion documentada que en escenas: una lectura por clave primaria."""
    device_id = _dispositivo_conectado(client)
    escena: dict[str, Any] = client.post(
        "/api/v1/scenes",
        json={
            "name": "Noche",
            "targets": [{"device_id": device_id, "effect_id": str(EFECTO.id)}],
        },
    ).json()
    creado: dict[str, Any] = client.post(
        "/api/v1/profiles",
        json={"name": "Sleep", "scenes": [{"scene_id": escena["id"]}]},
    ).json()
    LoopAwareProfileRepository.calls.pop("get", None)

    assert client.post(f"/api/v1/profiles/{creado['id']}/activate").status_code == 200

    assert LoopAwareProfileRepository.calls["get"] == [True]
