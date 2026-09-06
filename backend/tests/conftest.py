from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.app.config import Settings


@pytest.fixture
def spa_dist(tmp_path: Path) -> Path:
    """Un directorio que imita la salida de `npm run build`."""
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>LED Room</title>", encoding="utf-8")
    (assets / "index-abc123.js").write_text("console.log('led-room')", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name":"LED Room"}', encoding="utf-8")
    return dist


@pytest.fixture
def settings_with_spa(spa_dist: Path, tmp_path: Path) -> Settings:
    return Settings(frontend=spa_dist, database=tmp_path / "led-room.db")


@pytest.fixture
def settings_without_spa(tmp_path: Path) -> Settings:
    return Settings(frontend=tmp_path / "no-existe", database=tmp_path / "led-room.db")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Evita que un .env o variables del host contaminen los tests."""
    for name in list(dict(__import__("os").environ)):
        if name.startswith("LED_ROOM_"):
            monkeypatch.delenv(name, raising=False)
    yield
