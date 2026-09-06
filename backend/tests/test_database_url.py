"""La conversion ruta -> URL debe funcionar en Windows Y en el contenedor."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from backend.app.config import Settings
from backend.app.infrastructure.persistence.database import (
    build_database_url,
    url_from_absolute_path,
)


def test_url_de_ruta_posix_absoluta_lleva_cuatro_barras() -> None:
    # El caso del contenedor: LED_ROOM_DATABASE=/data/led-room.db
    assert url_from_absolute_path(PurePosixPath("/data/led-room.db")) == (
        "sqlite:////data/led-room.db"
    )


def test_url_de_ruta_windows_usa_barras_normales() -> None:
    windows_path = PureWindowsPath("C:\\repo\\data\\led-room.db")
    assert url_from_absolute_path(windows_path) == ("sqlite:///C:/repo/data/led-room.db")


def test_build_database_url_devuelve_una_ruta_absoluta(tmp_path: Path) -> None:
    url = build_database_url(tmp_path / "led-room.db")
    assert url.startswith("sqlite:///")
    assert url.endswith("/led-room.db")


def test_la_url_sale_del_valor_configurado(tmp_path: Path) -> None:
    settings = Settings(database=tmp_path / "sub" / "led-room.db")
    assert build_database_url(settings.database).endswith("/sub/led-room.db")
