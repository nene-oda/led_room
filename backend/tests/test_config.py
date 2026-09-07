from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from backend.app.config import ConfigurationError, Settings, get_settings
from backend.app.domain.devices.models import DeviceType


@pytest.fixture
def _sin_ajustes_cacheados() -> Iterator[None]:
    """`get_settings` memoriza: sin limpiar la cache el test contamina al resto."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_valores_por_defecto() -> None:
    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.device_name == "ELK-BLEDOM"
    assert settings.device_adapter.value == "null"
    assert settings.device_discovery is None
    assert settings.ble_scan_name_filter is False
    assert settings.ble_scan_timeout == 10.0
    assert settings.ble_connect_timeout == 20.0
    assert settings.ble_write_timeout == 5.0
    assert settings.ble_max_updates_per_second == 20
    assert settings.effect_fps == 20
    assert settings.log_level == "INFO"


def test_el_adaptador_configurado_es_el_enum_del_dominio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un solo vocabulario de adaptador en configuracion, dominio y base."""
    assert Settings().device_adapter is DeviceType.NULL

    monkeypatch.setenv("LED_ROOM_DEVICE_ADAPTER", "lotus_lantern")

    assert Settings().device_adapter is DeviceType.LOTUS_LANTERN


def test_por_defecto_descubre_la_misma_familia_que_controla() -> None:
    """Sin `LED_ROOM_DEVICE_DISCOVERY` no cambia nada: una sola palanca."""
    assert Settings().discovery_adapter is DeviceType.NULL
    assert Settings(device_adapter=DeviceType.LOTUS_LANTERN).discovery_adapter is (
        DeviceType.LOTUS_LANTERN
    )


def test_descubrir_y_controlar_se_pueden_configurar_por_separado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Es lo que permite usar la radio del PC antes de que exista el control BLE."""
    monkeypatch.setenv("LED_ROOM_DEVICE_DISCOVERY", "lotus_lantern")

    settings = Settings()

    assert settings.device_adapter is DeviceType.NULL
    assert settings.discovery_adapter is DeviceType.LOTUS_LANTERN


def test_el_filtro_por_nombre_esta_apagado_y_al_encenderlo_usa_device_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un escaneo que filtra de serie esconde la tira que se intenta encontrar."""
    assert Settings().scan_name_filter is None

    monkeypatch.setenv("LED_ROOM_BLE_SCAN_NAME_FILTER", "1")

    assert Settings().scan_name_filter == "ELK-BLEDOM"


def test_un_adaptador_desconocido_se_rechaza_al_arrancar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuracion invalida = fallo duro, no arranque degradado (NEXT_STEPS A6)."""
    monkeypatch.setenv("LED_ROOM_DEVICE_ADAPTER", "wled")

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("updates", ["0", "61"])
def test_frecuencia_de_escritura_fuera_de_rango_falla(
    monkeypatch: pytest.MonkeyPatch, updates: str
) -> None:
    monkeypatch.setenv("LED_ROOM_BLE_MAX_UPDATES_PER_SECOND", updates)

    with pytest.raises(ValidationError):
        Settings()


def test_variable_de_entorno_respetada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LED_ROOM_PORT", "9000")

    assert Settings().port == 9000


def test_puerto_no_numerico_falla_con_error_de_validacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LED_ROOM_PORT", "no-es-un-puerto")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "port" in str(excinfo.value)


@pytest.mark.parametrize("fps", ["0", "61"])
def test_fps_fuera_de_rango_falla(monkeypatch: pytest.MonkeyPatch, fps: str) -> None:
    monkeypatch.setenv("LED_ROOM_EFFECT_FPS", fps)

    with pytest.raises(ValidationError):
        Settings()


def test_nivel_de_log_se_normaliza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LED_ROOM_LOG_LEVEL", "debug")

    assert Settings().log_level == "DEBUG"


def test_duracion_de_fotograma_derivada_de_los_fps() -> None:
    """README 12: transition 4000 ms a 20 fps -> 80 fotogramas de 50 ms."""
    assert Settings().frame_duration_ms == 50


def test_el_intervalo_de_throttling_no_depende_de_los_fps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subir los fps de un efecto no debe inundar el enlace BLE (README 18)."""
    monkeypatch.setenv("LED_ROOM_EFFECT_FPS", "60")
    settings = Settings()

    assert settings.frame_duration_ms == 17
    assert settings.throttle_interval_ms == 50


# --- Una variable de entorno vacia equivale a no haberla definido -------------
#
# Regresion del incidente que dejaba el contenedor sin arrancar: Compose no
# omite `LED_ROOM_DEVICE_DISCOVERY: ${LED_ROOM_DEVICE_DISCOVERY:-}` cuando la
# variable no existe en el host, la inyecta vacia. Con `str` no pasaba nada,
# pero `''` no es miembro de `DeviceType`, ni un `float`, ni un `bool`, ni un
# `LogLevel`, y `Settings()` moria en el arranque.


def test_la_familia_de_descubrimiento_vacia_no_impide_arrancar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El caso exacto del incidente: el contenedor moria antes de servir nada."""
    monkeypatch.setenv("LED_ROOM_DEVICE_DISCOVERY", "")

    settings = Settings()

    assert settings.device_discovery is None
    assert settings.discovery_adapter is DeviceType.NULL


def test_todas_las_variables_vacias_dejan_los_valores_por_defecto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vale para cualquier campo, incluidos los que se anadan despues."""
    por_defecto = Settings()

    for campo in Settings.model_fields:
        monkeypatch.setenv(f"LED_ROOM_{campo.upper()}", "")

    assert Settings() == por_defecto


@pytest.mark.parametrize(
    "variable",
    [
        "LED_ROOM_PORT",
        "LED_ROOM_DATABASE",
        "LED_ROOM_FRONTEND",
        "LED_ROOM_DEVICE_ADAPTER",
        "LED_ROOM_DEVICE_DISCOVERY",
        "LED_ROOM_DEVICE_NAME",
        "LED_ROOM_BLE_SCAN_TIMEOUT",
        "LED_ROOM_BLE_SCAN_NAME_FILTER",
        "LED_ROOM_BLE_CONNECT_TIMEOUT",
        "LED_ROOM_BLE_WRITE_TIMEOUT",
        "LED_ROOM_BLE_MAX_UPDATES_PER_SECOND",
        "LED_ROOM_EFFECT_FPS",
        "LED_ROOM_LOG_LEVEL",
    ],
)
def test_una_variable_vacia_no_rompe_el_resto_de_la_configuracion(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    por_defecto = Settings()

    monkeypatch.setenv(variable, "")

    assert Settings() == por_defecto


def test_una_ruta_vacia_no_se_convierte_en_el_directorio_actual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Path('')` es `.`: sin este filtro SQLite recibiria un directorio."""
    por_defecto = Settings().database

    monkeypatch.setenv("LED_ROOM_DATABASE", "")

    assert Settings().database == por_defecto
    assert Settings().database.name == "led-room.db"


def test_solo_espacios_tambien_cuenta_como_ausente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LED_ROOM_DEVICE_DISCOVERY: " "` en un YAML entrecomillado es lo mismo."""
    monkeypatch.setenv("LED_ROOM_DEVICE_DISCOVERY", "   ")

    assert Settings().device_discovery is None


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("LED_ROOM_DEVICE_DISCOVERY", "lotus_lanturn"),
        ("LED_ROOM_DEVICE_ADAPTER", "wled"),
        ("LED_ROOM_PORT", "no-es-un-puerto"),
        ("LED_ROOM_BLE_SCAN_TIMEOUT", "pronto"),
        ("LED_ROOM_BLE_SCAN_NAME_FILTER", "quizas"),
        ("LED_ROOM_EFFECT_FPS", "muchos"),
        ("LED_ROOM_LOG_LEVEL", "verboso"),
    ],
)
def test_un_valor_presente_pero_invalido_sigue_fallando(
    monkeypatch: pytest.MonkeyPatch, variable: str, valor: str
) -> None:
    """Tolerar la ausencia no es tolerar la configuracion equivocada."""
    monkeypatch.setenv(variable, valor)

    with pytest.raises(ValidationError):
        Settings()


# --- Diagnostico de arranque -------------------------------------------------


@pytest.mark.usefixtures("_sin_ajustes_cacheados")
def test_una_configuracion_invalida_nombra_la_variable_y_el_valor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En un contenedor, el log de arranque es la unica pista del operador."""
    monkeypatch.setenv("LED_ROOM_DEVICE_DISCOVERY", "lotus_lanturn")

    with pytest.raises(ConfigurationError) as excinfo:
        get_settings()

    mensaje = str(excinfo.value)
    assert "LED_ROOM_DEVICE_DISCOVERY" in mensaje
    assert "lotus_lanturn" in mensaje
    assert "'null' or 'lotus_lantern'" in mensaje


@pytest.mark.usefixtures("_sin_ajustes_cacheados")
def test_el_diagnostico_reune_todos_los_errores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corregir de uno en uno reiniciando el contenedor no es aceptable."""
    monkeypatch.setenv("LED_ROOM_PORT", "99999")
    monkeypatch.setenv("LED_ROOM_EFFECT_FPS", "0")

    with pytest.raises(ConfigurationError) as excinfo:
        get_settings()

    mensaje = str(excinfo.value)
    assert "LED_ROOM_PORT" in mensaje
    assert "LED_ROOM_EFFECT_FPS" in mensaje


@pytest.mark.usefixtures("_sin_ajustes_cacheados")
def test_una_configuracion_valida_se_memoriza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LED_ROOM_DEVICE_DISCOVERY", "")

    assert get_settings() is get_settings()
