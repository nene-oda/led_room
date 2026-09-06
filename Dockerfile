# syntax=docker/dockerfile:1.9

################################################################
# Etapa 1 — Frontend (React + TypeScript + Vite)
################################################################
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

ENV CI=true \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false

# Capa cacheable: solo el manifiesto y el lockfile. npm ci exige
# package-lock.json y falla duro sin el, que es lo que queremos.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# El `test -f` convierte un build silenciosamente vacio en un fallo de
# construccion, en vez de una imagen sin frontend.
RUN npm run build && test -f /frontend/dist/index.html


################################################################
# Etapa 2 — Backend (entorno virtual aislado)
################################################################
FROM python:3.13-slim AS backend-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Compiladores SOLO en esta etapa: hacen falta si en alguna arquitectura no
# existe rueda precompilada. No llegan a la imagen final.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Capa cacheable de dependencias: se invalida solo cuando cambian, no con cada
# cambio de codigo. El paquete stub satisface a setuptools sin copiar la app.
COPY pyproject.toml /src/pyproject.toml
RUN mkdir -p /src/backend/app \
 && touch /src/backend/__init__.py /src/backend/app/__init__.py \
 && pip install /src

# Codigo real: reinstala el paquete sin volver a resolver dependencias.
COPY backend/ /src/backend/
COPY alembic.ini /src/alembic.ini
COPY alembic/ /src/alembic/
RUN pip install --no-deps --force-reinstall /src \
 && python -c "import backend.app.main" \
 && python -c "import backend.app.infrastructure.persistence.models" \
 && cd /src \
 && test "$(alembic -c alembic.ini heads | wc -l)" -eq 1


################################################################
# Etapa 3 — Runtime
################################################################
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="LED Room Controller" \
      org.opencontainers.image.description="Control de tira LED BLE desde la red local" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ARG LED_ROOM_UID=10001
ARG LED_ROOM_GID=10001

# NOTA SOBRE BLUETOOTH: no se instalan bluetooth, bluez ni dbus.
# El backend BlueZ de Bleak habla D-Bus con una biblioteca de Python puro
# contra el bus del sistema del HOST, montado como socket; no necesita el
# demonio bluetoothd ni las utilidades de linea de comandos dentro del
# contenedor. Instalarlos costaria ~100 MB sin aportar nada al camino real.
# Si la Fase 0 demuestra con hardware delante que hacen falta, se añade bluez
# aqui — nunca --privileged. Ver design.md D6.

RUN groupadd --gid "${LED_ROOM_GID}" ledroom \
 && useradd --uid "${LED_ROOM_UID}" --gid "${LED_ROOM_GID}" \
            --create-home --shell /usr/sbin/nologin ledroom \
 && mkdir -p /data /app \
 && chown -R ledroom:ledroom /data /app

COPY --from=backend-builder --chown=ledroom:ledroom /opt/venv /opt/venv
COPY --from=frontend-builder --chown=ledroom:ledroom /frontend/dist /app/frontend

# Migraciones: se copian del contexto, no del builder, para que anadir una
# revision no invalide la capa del entorno virtual.
COPY --chown=ledroom:ledroom alembic.ini /app/alembic.ini
COPY --chown=ledroom:ledroom alembic/ /app/alembic/

# --chmod garantiza el bit de ejecucion aunque el contexto venga de Windows,
# donde el modo del archivo no se preserva.
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LED_ROOM_HOST=0.0.0.0 \
    LED_ROOM_PORT=8000 \
    LED_ROOM_DATABASE=/data/led-room.db \
    LED_ROOM_FRONTEND=/app/frontend \
    LED_ROOM_DEVICE_ADAPTER=null \
    LED_ROOM_BLE_SCAN_TIMEOUT=10 \
    LED_ROOM_EFFECT_FPS=20 \
    LED_ROOM_LOG_LEVEL=INFO
# LED_ROOM_DEVICE_NAME se deja SIN valor por defecto en la imagen: es
# configuracion del despliegue, no del artefacto. Nunca se hornea una MAC aqui.

WORKDIR /app
USER ledroom
EXPOSE 8000

# Sin VOLUME /data a proposito: crearia volumenes anonimos en cada docker run
# sin -v y confundiria la persistencia. El volumen es explicito en run/compose.

# start-period ampliado: el arranque incluye ahora 'alembic upgrade head'.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('LED_ROOM_PORT', '8000') + '/api/v1/health', timeout=3)"]

# sh -c para expandir las variables; exec para que uvicorn quede como PID 1 y
# reciba SIGTERM (sin el, docker stop esperaria 10 s y cerraria BLE en sucio).
# Un solo worker SIEMPRE: varios romperian el estado global autoritativo, el
# difundido por WebSocket y abririan varias conexiones BLE al mismo
# controlador. Ver design.md D9.
# El entrypoint aplica el esquema y CEDE el proceso al CMD con exec, de modo
# que uvicorn sigue siendo PID 1 y recibe SIGTERM. El CMD NO cambia. Ver D9.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host \"$LED_ROOM_HOST\" --port \"$LED_ROOM_PORT\""]
