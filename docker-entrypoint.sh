#!/bin/sh
# Entrypoint del contenedor LED Room.
#
# Aplica el esquema de la base de datos y CEDE el proceso al CMD mediante exec,
# de modo que uvicorn siga siendo PID 1 y reciba SIGTERM directamente. Sin ese
# exec final, `docker stop` esperaria el grace period completo y cerraria la
# conexion BLE en sucio. Ver design.md D9.
set -eu

: "${LED_ROOM_DATABASE:=/data/led-room.db}"
: "${LED_ROOM_MIGRATE:=1}"
: "${LED_ROOM_MIGRATE_LOCK_TIMEOUT:=60}"

DATA_DIR=$(dirname "$LED_ROOM_DATABASE")

if [ "$LED_ROOM_MIGRATE" = "1" ]; then
    mkdir -p "$DATA_DIR" 2>/dev/null || true

    # SQLite no solo escribe el .db: necesita crear los archivos -wal y -shm
    # HERMANOS, asi que hace falta permiso de escritura sobre el DIRECTORIO.
    if [ ! -w "$DATA_DIR" ]; then
        echo "led-room: el directorio de datos '$DATA_DIR' no es escribible por UID $(id -u):$(id -g)." >&2
        echo "led-room: bind mount -> 'sudo chown -R $(id -u):$(id -g) <dir-del-host>'." >&2
        echo "led-room: alternativa sin friccion -> volumen nombrado (-v led-room-data:/data)." >&2
        exit 78   # EX_CONFIG: error de configuracion, no de codigo.
    fi

    # SQLite NO serializa dos 'alembic upgrade head' simultaneos: el segundo
    # muere con 'table ... already exists'. El cerrojo si lo hace.
    exec 9>"$DATA_DIR/.migrate.lock"
    if ! flock -w "$LED_ROOM_MIGRATE_LOCK_TIMEOUT" 9; then
        echo "led-room: otra instancia sigue migrando tras ${LED_ROOM_MIGRATE_LOCK_TIMEOUT}s." >&2
        exit 75   # EX_TEMPFAIL: reintentable por la politica de reinicio.
    fi

    echo "led-room: aplicando migraciones sobre ${LED_ROOM_DATABASE}"
    alembic -c /app/alembic.ini upgrade head
    echo "led-room: esquema al dia"

    # Liberar el cerrojo ANTES del exec: si no, uvicorn heredaria el descriptor
    # y lo mantendria tomado durante toda la vida del contenedor.
    exec 9>&-
else
    echo "led-room: LED_ROOM_MIGRATE=0; migraciones omitidas"
fi

exec "$@"
