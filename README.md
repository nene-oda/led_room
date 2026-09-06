# LED Room Controller — Arquitectura y plan de implementación

> Proyecto personal para controlar una tira LED compatible con **LotusLantern / BLE** desde una interfaz web accesible desde PC, Android y iPhone, con soporte para colores, brillo, escenas, perfiles y efectos personalizados.

---

## 1. Objetivo

Construir una aplicación autocontenida que permita controlar las luces LED del cuarto desde cualquier dispositivo conectado a la misma red local.

La aplicación debe permitir:

- Encender y apagar las luces.
- Seleccionar colores RGB.
- Ajustar brillo.
- Crear transiciones suaves entre colores.
- Crear efectos personalizados.
- Crear y guardar escenas.
- Seleccionar perfiles o modos predefinidos.
- Ejecutar secuencias de colores en loop.
- Cambiar velocidad e intensidad de los efectos.
- Acceder desde:
  - PC.
  - Android.
  - iPhone.
  - Tablet.
- Ejecutarse inicialmente en una computadora personal.
- Poder migrarse posteriormente a:
  - Raspberry Pi.
  - Mini PC.
  - Servidor Linux.
- Iniciarse mediante Docker.

---

# 2. Restricción del hardware actual

El controlador actual utiliza:

- Bluetooth.
- Aplicación compatible: **LotusLantern**.
- Control remoto 2.4 GHz.
- Alimentación DC 5–24 V.
- Control RGB, brillo, modos y ritmo musical.

El hardware parece corresponder a una tira RGB convencional.

Esto implica que, probablemente, toda la tira utiliza un único color simultáneamente.

Por ejemplo:

```text
AZUL AZUL AZUL AZUL AZUL AZUL
```

y no:

```text
AZUL AZUL MORADO MORADO ROSA ROSA
```

Por lo tanto, una mezcla como:

```text
azul → morado → rosa
```

se implementará inicialmente como una **transición temporal**:

```text
t=0s      Azul
t=1s      Azul-violeta
t=2s      Morado
t=3s      Morado-rosa
t=4s      Rosa
```

La arquitectura se diseñará para que en el futuro sea posible agregar tiras direccionables como:

- WS2812B.
- WS2815.
- SK6812.

sin cambiar el frontend.

---

# 3. Arquitectura general

```text
                     RED LOCAL / WI-FI

 ┌──────────────┐
 │    iPhone    │
 │ Safari / PWA │
 └──────┬───────┘
        │
 ┌──────▼───────┐
 │   Android    │
 │ Chrome / PWA │
 └──────┬───────┘
        │
 ┌──────▼───────┐
 │      PC      │
 │   Browser    │
 └──────┬───────┘
        │
        │ HTTP + WebSocket
        ▼
┌─────────────────────────────────────┐
│          LED ROOM SERVER            │
│                                     │
│  ┌───────────────────────────────┐  │
│  │ Frontend React + TypeScript   │  │
│  └──────────────┬────────────────┘  │
│                 │                   │
│  ┌──────────────▼────────────────┐  │
│  │ FastAPI                       │  │
│  │ REST API + WebSocket          │  │
│  └──────────────┬────────────────┘  │
│                 │                   │
│  ┌──────────────▼────────────────┐  │
│  │ Effects Engine                │  │
│  │ Scenes / Profiles / Timeline  │  │
│  └──────────────┬────────────────┘  │
│                 │                   │
│  ┌──────────────▼────────────────┐  │
│  │ Device Adapter                │  │
│  │ LotusLantern BLE             │  │
│  └──────────────┬────────────────┘  │
│                 │                   │
│              Bleak                  │
└─────────────────┼───────────────────┘
                  │
                  │ Bluetooth BLE
                  ▼
          ┌───────────────────┐
          │ LotusLantern LED  │
          │    Controller     │
          └───────────────────┘
```

---

# 4. Stack recomendado

## Frontend

```text
React
TypeScript
Vite
```

Opcionales:

```text
TanStack Query
Zustand
React Router
```

La aplicación será una SPA.

No se requiere SSR, por lo que Vite resulta más simple que Next.js para este proyecto.

---

## Backend

```text
Python
FastAPI
Pydantic
Bleak
WebSockets
SQLModel
```

Responsabilidades:

- Descubrir dispositivos BLE.
- Conectarse al controlador.
- Enviar comandos RGB.
- Ejecutar efectos.
- Mantener estado.
- Guardar escenas.
- Exponer REST API.
- Mantener WebSocket con los clientes.

---

## Persistencia

Para la primera versión:

```text
SQLite
```

Ejemplo:

```text
/data/led-room.db
```

Más adelante podría cambiarse por PostgreSQL sin modificar el dominio.

---

# 5. Arquitectura por capas

```text
┌─────────────────────────────────┐
│ Presentation                    │
│ React / REST / WebSocket        │
├─────────────────────────────────┤
│ Application                     │
│ Commands / Use Cases            │
├─────────────────────────────────┤
│ Domain                          │
│ Device / Scene / Effect/Profile │
├─────────────────────────────────┤
│ Infrastructure                  │
│ BLE / SQLite / repositories     │
└─────────────────────────────────┘
```

---

# 6. Estructura propuesta del repositorio

```text
led-room/
│
├── README.md
├── ARCHITECTURE.md
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .env.example
│
├── pyproject.toml          ← en la RAÍZ (ver ARCHITECTURE.md §5.1)
│
├── backend/
│   │
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   │
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── devices.py
│   │   │   ├── lights.py
│   │   │   ├── scenes.py
│   │   │   ├── profiles.py
│   │   │   └── effects.py
│   │   │
│   │   ├── domain/
│   │   │   ├── devices/
│   │   │   │   ├── models.py
│   │   │   │   └── ports.py
│   │   │   │
│   │   │   ├── effects/
│   │   │   │   ├── models.py
│   │   │   │   ├── engine.py
│   │   │   │   └── interpolators.py
│   │   │   │
│   │   │   ├── scenes/
│   │   │   │   ├── models.py
│   │   │   │   └── services.py
│   │   │   │
│   │   │   └── profiles/
│   │   │       └── models.py
│   │   │
│   │   ├── application/
│   │   │   ├── device_service.py
│   │   │   ├── light_service.py
│   │   │   ├── effect_service.py
│   │   │   ├── scene_service.py
│   │   │   └── profile_service.py
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── bluetooth/
│   │   │   │   ├── scanner.py
│   │   │   │   ├── lotus_lantern.py
│   │   │   │   ├── protocol.py
│   │   │   │   └── commands.py
│   │   │   │
│   │   │   └── persistence/
│   │   │       ├── database.py
│   │   │       ├── scene_repository.py
│   │   │       └── profile_repository.py
│   │   │
│   │   └── websocket/
│   │       ├── manager.py
│   │       └── events.py
│   │
│   └── tests/
│
├── frontend/
│   │
│   ├── package.json
│   ├── vite.config.ts
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       │
│       ├── api/
│       │   ├── client.ts
│       │   └── websocket.ts
│       │
│       ├── components/
│       │   ├── ColorPicker/
│       │   ├── BrightnessSlider/
│       │   ├── DeviceStatus/
│       │   ├── EffectEditor/
│       │   └── SceneCard/
│       │
│       ├── pages/
│       │   ├── Home.tsx
│       │   ├── Scenes.tsx
│       │   ├── Effects.tsx
│       │   ├── Profiles.tsx
│       │   └── Settings.tsx
│       │
│       └── domain/
│           ├── effects.ts
│           ├── scenes.ts
│           └── devices.ts
│
└── data/
    └── .gitkeep
```

---

# 7. Dominio

## Device

Representa un controlador físico.

```typescript
interface Device {
  id: string
  name: string
  address: string
  type: DeviceType
  connected: boolean
  capabilities: DeviceCapabilities
}
```

---

## DeviceCapabilities

Permite soportar hardware diferente sin cambiar la interfaz.

```typescript
interface DeviceCapabilities {
  rgb: boolean
  brightness: boolean
  effects: boolean
  addressable: boolean
  segments: boolean
  whiteChannel: boolean
}
```

Ejemplo del hardware actual:

```json
{
  "rgb": true,
  "brightness": true,
  "effects": true,
  "addressable": false,
  "segments": false,
  "whiteChannel": false
}
```

Una futura WS2812 podría tener:

```json
{
  "rgb": true,
  "brightness": true,
  "effects": true,
  "addressable": true,
  "segments": true,
  "whiteChannel": false
}
```

---

# 8. Colores

Modelo:

```json
{
  "r": 130,
  "g": 20,
  "b": 255
}
```

También se podrá trabajar con hexadecimal:

```text
#8214FF
```

---

# 9. Efectos

Un efecto describe cómo cambia la luz en el tiempo.

Ejemplo:

```json
{
  "id": "cyberpunk-wave",
  "name": "Cyberpunk",
  "type": "smooth_cycle",
  "colors": [
    "#009DFF",
    "#7B00FF",
    "#FF008C"
  ],
  "brightness": 60,
  "speed": 50,
  "transition_ms": 3500,
  "loop": true
}
```

---

# 10. Tipos de efecto iniciales

## Static

```text
████████████████

#7B00FF
```

---

## Smooth Cycle

```text
BLUE
 ↓
PURPLE
 ↓
PINK
 ↓
BLUE
```

---

## Pulse

```text
Brightness

100 ┤       ╭──╮
 75 ┤     ╭─╯  ╰─╮
 50 ┤   ╭─╯      ╰─╮
 25 ┤ ╭─╯          ╰─╮
  0 ┼──────────────────
```

---

## Breathing

Combina:

```text
color interpolation
+
brightness interpolation
```

---

## Flash

```text
ON
OFF
ON
OFF
```

con velocidad configurable.

---

## Random

Selecciona colores aleatorios de una paleta.

---

## Sunset

Transición lenta:

```text
amarillo
 ↓
naranja
 ↓
rojo
 ↓
magenta
 ↓
violeta
```

---

## Gaming

Ejemplo:

```text
azul
 ↓
morado
 ↓
rosa
 ↓
morado
 ↓
azul
```

---

# 11. Motor de efectos

El backend será quien genere los frames.

Ejemplo:

```text
Effect
   │
   ▼
Interpolator
   │
   ▼
Frame Generator
   │
   ▼
Device Adapter
   │
   ▼
BLE
```

---

## Frame

```python
class LightFrame:
    color: RGBColor
    brightness: int
    duration_ms: int
```

Ejemplo:

```json
{
  "color": "#7B22FF",
  "brightness": 65,
  "duration_ms": 50
}
```

---

# 12. Interpolación de colores

Para transiciones suaves:

```text
A = #003CFF
B = #7B00FF
```

el servidor generará:

```text
#003CFF
#1037FF
#2132FF
#312DFF
#4228FF
#5222FF
#6319FF
#7310FF
#7B00FF
```

La cantidad de pasos dependerá de:

```text
transition_ms
fps
```

Por ejemplo:

```text
transition = 4000 ms
fps = 20

frames = 80
```

---

# 13. Scene

Una escena representa una configuración completa.

Ejemplo:

```json
{
  "id": "night",
  "name": "Noche",
  "icon": "moon",
  "brightness": 10,
  "effect": {
    "type": "static",
    "colors": [
      "#001533"
    ]
  }
}
```

Otro ejemplo:

```json
{
  "id": "america",
  "name": "América",
  "effect": {
    "type": "smooth_cycle",
    "colors": [
      "#FFD500",
      "#003DA5"
    ],
    "transition_ms": 2500,
    "loop": true
  }
}
```

---

# 14. Profiles

Un perfil agrupa escenas y preferencias para un contexto.

Ejemplos:

```text
Work
Gaming
Relax
Sleep
Party
Movie
América
```

Ejemplo:

```json
{
  "name": "Gaming",
  "default_scene": "cyberpunk",
  "brightness_limit": 75,
  "scenes": [
    "cyberpunk",
    "purple-pulse",
    "blue-wave"
  ]
}
```

---

# 15. Perfiles iniciales

## Work

```text
Brightness: 45%
Color: blanco frío / azul claro
Animation: mínima
```

---

## Relax

```text
Brightness: 25%
Colors:
- naranja
- rosa
- violeta

Transition:
slow
```

---

## Gaming

```text
Brightness: 55%

Colors:
- cyan
- azul
- morado
- magenta
```

---

## Sleep

```text
Brightness: 5–10%

Color:
azul muy oscuro
o
rojo tenue
```

---

## Party

```text
Brightness: 80%

Transitions:
rápidas

Effects:
flash
random
pulse
```

---

# 16. API

Base:

```text
/api/v1
```

---

## Health

```http
GET /api/v1/health
```

Respuesta:

```json
{
  "status": "ok"
}
```

---

## Buscar dispositivos

```http
GET /api/v1/devices/scan
```

Respuesta:

```json
[
  {
    "name": "ELK-BLEDOM",
    "address": "XX:XX:XX:XX:XX:XX",
    "rssi": -51
  }
]
```

---

## Conectar

```http
POST /api/v1/devices/{device_id}/connect
```

---

## Estado

```http
GET /api/v1/devices/{device_id}
```

---

## Encender

```http
POST /api/v1/lights/power
```

```json
{
  "on": true
}
```

---

## Cambiar color

```http
PUT /api/v1/lights/color
```

```json
{
  "r": 123,
  "g": 0,
  "b": 255
}
```

---

## Brillo

```http
PUT /api/v1/lights/brightness
```

```json
{
  "brightness": 65
}
```

---

## Ejecutar escena

```http
POST /api/v1/scenes/{scene_id}/activate
```

---

## Crear escena

```http
POST /api/v1/scenes
```

---

## Crear perfil

```http
POST /api/v1/profiles
```

---

# 17. WebSocket

Endpoint:

```text
/ws
```

Se utilizará para controles que necesiten baja latencia.

Por ejemplo, cuando se arrastre el selector RGB:

```json
{
  "type": "light.color",
  "payload": {
    "r": 121,
    "g": 38,
    "b": 255
  }
}
```

---

## Eventos del servidor

```text
device.connected
device.disconnected

light.power.changed
light.color.changed
light.brightness.changed

effect.started
effect.stopped

scene.activated
```

---

# 18. Control en tiempo real

```text
Color Picker
    │
    │ WebSocket
    ▼
FastAPI
    │
    ▼
LedService
    │
    ▼
BLE
    │
    ▼
LED
```

Se deberá aplicar throttling.

Por ejemplo:

```text
20 actualizaciones / segundo
```

en lugar de mandar cientos de comandos innecesarios.

---

# 19. BLE Adapter

El dominio no debe conocer Bleak directamente.

Interfaz:

```python
class LightDevicePort(Protocol):

    async def connect(self) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def set_power(self, value: bool) -> None:
        ...

    async def set_color(
        self,
        red: int,
        green: int,
        blue: int
    ) -> None:
        ...

    async def set_brightness(
        self,
        brightness: int
    ) -> None:
        ...
```

Implementación:

```text
LotusLanternBLEAdapter
```

Más adelante:

```text
WLEDAdapter
ESP32Adapter
HueAdapter
```

---

# 20. Docker

La aplicación deberá poder construirse como una sola imagen.

```text
Frontend build
      │
      ▼
React static files
      │
      ▼
FastAPI
      │
      ▼
Docker Image
```

FastAPI podrá servir también el frontend compilado.

De esta manera solo se requiere ejecutar un contenedor.

---

# 21. Dockerfile conceptual

```dockerfile
# ---------- Frontend ----------
FROM node:22-alpine AS frontend

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend .
RUN npm run build


# ---------- Backend ----------
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bluetooth \
       bluez \
       dbus \
    && rm -rf /var/lib/apt/lists/*

COPY backend /app/backend

RUN pip install --no-cache-dir -e /app/backend

COPY --from=frontend /frontend/dist /app/frontend

ENV LED_ROOM_FRONTEND=/app/frontend

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **Nota de implementación.** El `Dockerfile` real difiere de este boceto en
> tres puntos, documentados con su razón en `ARCHITECTURE.md` §5:
>
> 1. `pip install -e /app/backend` **no** produce un paquete importable como
>    `backend.app`. El `pyproject.toml` vive en la raíz del repositorio y la
>    instalación se hace desde ahí.
> 2. No se instalan `bluetooth`, `bluez` ni `dbus`: Bleak habla D-Bus contra el
>    bus del sistema del host con una biblioteca de Python puro. Ahorra ~100 MB.
> 3. El `CMD` real usa `sh -c` con `exec`, para expandir `LED_ROOM_HOST` y
>    `LED_ROOM_PORT` y que uvicorn quede como PID 1 y reciba `SIGTERM`.

---

# 22. Construcción

Desde la raíz:

```bash
docker build -t led-room:latest .
```

---

# 23. Ejecución con Docker Run

En Linux, el contenedor necesitará acceso al Bluetooth del host.

Ejemplo inicial:

```bash
docker run \
  --name led-room \
  --restart unless-stopped \
  --network host \
  -v /var/run/dbus:/var/run/dbus \
  -v "$(pwd)/data:/data" \
  -e LED_ROOM_DATABASE=/data/led-room.db \
  led-room:latest
```

Abrir:

```text
http://localhost:8000
```

Desde otro dispositivo de la red:

```text
http://IP_DEL_PC:8000
```

Por ejemplo:

```text
http://192.168.1.70:8000
```

---

# 24. Docker Compose

Aunque el objetivo principal sea soportar `docker run`, también se puede incluir:

```yaml
services:

  led-room:

    build:
      context: .

    container_name: led-room

    restart: unless-stopped

    network_mode: host

    volumes:
      - /var/run/dbus:/var/run/dbus
      - ./data:/data

    environment:
      LED_ROOM_DATABASE: /data/led-room.db
```

Ejecutar:

```bash
docker compose up -d
```

> **Nota de implementación.** `network_mode: host` solo tiene semántica útil en
> Linux; en Docker Desktop no expone la red del host y además es incompatible
> con `ports`. Por eso la implementación reparte esto en dos archivos:
>
> - `docker-compose.yml` — portable, publica el puerto 8000. Funciona en
>   cualquier sistema, incluido Windows.
> - `compose.bluetooth.yml` — override para Linux y Raspberry Pi, que añade
>   `network_mode: host` y el montaje del bus del sistema.
>
> ```bash
> # En cualquier sistema
> docker compose up -d
>
> # En Linux / Raspberry Pi, con acceso al Bluetooth del host
> docker compose -f docker-compose.yml -f compose.bluetooth.yml up -d
> ```

---

# 25. Consideración importante: Bluetooth + Docker

Bluetooth no funciona igual en todos los hosts.

## Linux

Es la plataforma recomendada para ejecutar el contenedor BLE.

Normalmente se puede compartir:

```text
/var/run/dbus
```

con el contenedor.

---

## Raspberry Pi

Será una plataforma ideal posteriormente porque utiliza Linux y puede ejecutar la misma imagen Docker.

Ejemplo futuro:

```text
docker run led-room
```

sin cambiar la arquitectura.

---

## Windows + Docker Desktop

Docker Desktop ejecuta los contenedores dentro de una VM.

Por ello, el Bluetooth físico de Windows no siempre está disponible directamente dentro del contenedor Linux.

En Windows se contemplan dos estrategias:

### Estrategia A

Ejecutar temporalmente el backend BLE de forma nativa:

```text
Windows
│
├── Python + FastAPI + Bleak
│
└── Browser
```

### Estrategia B

Separar un pequeño `ble-agent` nativo:

```text
Docker
│
│ HTTP
▼
ble-agent
│
│ BLE
▼
LED
```

El resto de la aplicación seguirá funcionando en Docker.

La arquitectura debe mantener esta posibilidad desde el inicio mediante `LightDevicePort`.

---

# 26. Variables de entorno

`.env.example`

```env
LED_ROOM_HOST=0.0.0.0
LED_ROOM_PORT=8000

LED_ROOM_DATABASE=/data/led-room.db

# Ruta de los estáticos del SPA que sirve FastAPI.
LED_ROOM_FRONTEND=/app/frontend

# Implementación de LightDevicePort: null | lotus_lantern
# "null" no toca hardware y permite arrancar en cualquier host.
LED_ROOM_DEVICE_ADAPTER=null

LED_ROOM_DEVICE_NAME=ELK-BLEDOM

LED_ROOM_BLE_SCAN_TIMEOUT=10

LED_ROOM_EFFECT_FPS=20

LED_ROOM_LOG_LEVEL=INFO
```

`LED_ROOM_FRONTEND` y `LED_ROOM_DEVICE_ADAPTER` no estaban en el plan original;
el empaquetado los necesita. Fuera del contenedor, la base de datos y los
estáticos tienen valores por defecto **relativos al repositorio**, para que el
backend nativo funcione en Windows, donde `/data` no existe.

---

# 27. UI propuesta

Pantalla principal:

```text
┌──────────────────────────────────────┐
│ Bedroom LED                    ● BLE │
│                                      │
│               ON                     │
│                                      │
│             COLOR                    │
│                                      │
│              🎨                      │
│                                      │
│ Brightness                           │
│ ━━━━━━━━━━━━━●━━━━━━━━ 62%           │
│                                      │
│ QUICK SCENES                         │
│                                      │
│ Gaming   Relax   Sleep   América     │
│                                      │
│ CURRENT EFFECT                       │
│                                      │
│ Cyberpunk Smooth                     │
│                                      │
│ Speed                                │
│ ━━━━━━━●━━━━━━━━━━━━━━ 42%           │
└──────────────────────────────────────┘
```

---

# 28. Editor de efectos

```text
CREATE EFFECT

Name
Cyberpunk Night

Colors

[ #009DFF ]
       +
[ #7B00FF ]
       +
[ #FF008C ]

Transition

Smooth

Duration

3.5 seconds

Brightness

60%

Loop

[x]

             Preview

      BLUE → PURPLE → PINK

          [ SAVE EFFECT ]
```

---

# 29. Editor de escenas

Una escena podrá seleccionar:

```text
name
icon
effect
brightness
speed
duration
auto-stop
```

Ejemplo:

```json
{
  "name": "Movie",
  "brightness": 15,
  "effect": "deep-blue-breathing",
  "auto_stop": null
}
```

---

# 30. Página Profiles

```text
PROFILES

┌───────────┐
│ 💻 Work   │
└───────────┘

┌───────────┐
│ 🎮 Gaming │
└───────────┘

┌───────────┐
│ 🌙 Sleep  │
└───────────┘

┌───────────┐
│ 🎬 Movie  │
└───────────┘

┌───────────┐
│ 🎉 Party  │
└───────────┘
```

---

# 31. Estado global

El servidor deberá conservar:

```json
{
  "device": {
    "connected": true
  },
  "light": {
    "power": true,
    "color": "#7B00FF",
    "brightness": 60
  },
  "effect": {
    "running": true,
    "id": "cyberpunk"
  },
  "scene": {
    "id": "gaming"
  }
}
```

Los navegadores conectados reciben las modificaciones vía WebSocket.

Esto permite que:

```text
iPhone cambia color

        ↓

PC actualiza automáticamente

        ↓

Android actualiza automáticamente
```

---

# 32. Seguridad inicial

Como se utilizará únicamente en la red local:

```text
LAN only
```

No es necesario comenzar con autenticación compleja.

Sin embargo, el servidor debe escuchar únicamente donde sea necesario y no debe exponerse directamente a Internet.

Posteriormente se puede agregar:

```text
PIN
JWT
Passkeys
Cloudflare Tunnel
Tailscale
```

si se requiere acceso remoto.

---

# 33. Roadmap

## Fase 0 — identificar controlador

Objetivo:

```text
PC
 ↓
BLE scan
 ↓
controller detected
```

Tareas:

- [ ] Identificar nombre BLE.
- [ ] Identificar UUIDs de servicios.
- [ ] Identificar característica de escritura.
- [ ] Probar comando ON.
- [ ] Probar comando OFF.
- [ ] Probar RGB.

---

# 34. Fase 1 — MVP Bluetooth

Backend únicamente.

```text
Python
 ↓
Bleak
 ↓
LED
```

Funciones:

- [ ] Scan.
- [ ] Connect.
- [ ] Disconnect.
- [ ] Power.
- [ ] Color.
- [ ] Brightness.

---

# 35. Fase 2 — API

```text
HTTP
 ↓
FastAPI
 ↓
BLE
```

Endpoints:

- [ ] `/devices`
- [ ] `/power`
- [ ] `/color`
- [ ] `/brightness`

---

# 36. Fase 3 — Web UI

```text
React
 ↓
FastAPI
 ↓
BLE
```

Pantalla:

- [ ] Estado.
- [ ] On/off.
- [ ] Color picker.
- [ ] Brillo.
- [ ] Presets.

---

# 37. Fase 4 — WebSocket

```text
React
 ⇅
WebSocket
 ⇅
FastAPI
```

Objetivo:

- [ ] cambios RGB instantáneos.
- [ ] sincronización entre clientes.
- [ ] estado BLE en vivo.

---

# 38. Fase 5 — Effects Engine

Agregar:

- [ ] Smooth.
- [ ] Pulse.
- [ ] Breath.
- [ ] Flash.
- [ ] Random.
- [ ] Sunset.
- [ ] Gaming.
- [ ] custom sequence.

---

# 39. Fase 6 — Scenes

- [ ] Crear.
- [ ] Editar.
- [ ] Eliminar.
- [ ] Duplicar.
- [ ] Activar.
- [ ] Favoritos.

---

# 40. Fase 7 — Profiles

- [ ] Work.
- [ ] Gaming.
- [ ] Sleep.
- [ ] Relax.
- [ ] Movie.
- [ ] Party.
- [ ] Custom.

---

# 41. Fase 8 — PWA

Convertir frontend en Progressive Web App.

Permitirá instalarlo como aplicación en:

```text
Android
iPhone
Desktop
```

y abrirlo desde un icono.

Visualmente funcionará como una app móvil, aunque el servidor siga ejecutándose en la PC.

---

# 42. Fase 9 — Automatizaciones

Ejemplos:

```text
23:30
 ↓
Sleep Mode

07:00
 ↓
Sunrise Effect
```

Modelo:

```json
{
  "time": "23:30",
  "scene": "sleep",
  "days": [
    "mon",
    "tue",
    "wed",
    "thu",
    "sun"
  ]
}
```

---

# 43. Fase 10 — Audio

Posible implementación futura:

```text
Microphone
 ↓
FFT
 ↓
Frequency bands
 ↓
Color mapping
 ↓
Effect Engine
```

Ejemplo:

```text
bass
 ↓
brightness

mid
 ↓
hue

treble
 ↓
flash
```

---

# 44. Fase 11 — Hardware direccionable

Si posteriormente se reemplaza la tira por:

```text
WS2812B
WS2815
SK6812
```

se agregará:

```text
AddressableLightDevice
```

sin modificar:

```text
Scenes
Profiles
Effects
Frontend
API
```

Solo cambiará el adapter.

---

# 45. Posible arquitectura futura con Raspberry Pi

```text
                    Wi-Fi

          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼

       iPhone     Android       PC
          │          │          │
          └──────────┼──────────┘
                     │
                     ▼

               Raspberry Pi

            Docker: led-room

                     │
                     │ Bluetooth
                     ▼

                 LED Strip
```

El mismo repositorio e imagen Docker podrán utilizarse.

---

# 46. Diseño del proyecto pensando en GitHub

Repositorio:

```text
led-room
```

Branches:

```text
main
develop
feature/*
fix/*
```

Ejemplos:

```text
feature/ble-scan
feature/rgb-control
feature/effects-engine
feature/scenes-ui
feature/profiles
```

---

# 47. CI inicial

GitHub Actions:

```text
Pull Request
     │
     ├── Python tests
     ├── Ruff
     ├── mypy
     ├── npm lint
     ├── npm test
     └── docker build
```

---

# 48. Releases

Tags:

```text
v0.1.0
v0.2.0
v1.0.0
```

Docker:

```text
ghcr.io/<user>/led-room:latest
ghcr.io/<user>/led-room:v1.0.0
```

Entonces sería posible ejecutar:

```bash
docker run \
  --name led-room \
  --restart unless-stopped \
  --network host \
  -v /var/run/dbus:/var/run/dbus \
  -v led-room-data:/data \
  ghcr.io/<user>/led-room:latest
```

---

# 49. Primera meta concreta

La primera versión que debería considerarse exitosa es:

```text
docker run
    │
    ▼

Browser
    │
    ▼

LED Room
    │
    ├── Connected ●
    │
    ├── ON/OFF
    │
    ├── Color Picker
    │
    └── Brightness
            │
            ▼
       Real LED Strip
```

Sin efectos todavía.

---

# 50. Segunda meta

```text
LED Room

├── Manual
│   ├── RGB
│   └── Brightness
│
├── Effects
│   ├── Smooth
│   ├── Breath
│   ├── Pulse
│   └── Custom
│
├── Scenes
│   ├── Gaming
│   ├── Relax
│   ├── Movie
│   └── América
│
└── Profiles
    ├── Work
    ├── Gaming
    ├── Sleep
    └── Party
```

---

# 51. Principio principal

La aplicación no debe quedar acoplada al controlador LotusLantern.

La relación debe ser:

```text
Application
     │
     ▼
LightDevicePort
     │
     ├──────────────┐
     │              │
     ▼              ▼

LotusLantern       WLED
BLE Adapter        Adapter

                     │
                     ▼

                  ESP32
```

Esto permitirá conservar todo el software cuando cambie el hardware.

---

# 52. Resumen

Stack:

```text
Frontend
React + TypeScript + Vite

Backend
FastAPI + Python

Realtime
WebSocket

Bluetooth
Bleak

Database
SQLite

Deployment
Docker

Initial Host
PC

Future Host
Raspberry Pi
```

Flujo actual:

```text
iPhone / Android / PC
          │
          │ Wi-Fi
          ▼
       Web App
          │
          ▼
       FastAPI
          │
          ▼
      BLE Adapter
          │
          │ Bluetooth
          ▼
    LotusLantern LED
```

Objetivo final:

```text
         LED ROOM

Manual Control
     +
Effects
     +
Scenes
     +
Profiles
     +
Automations
     +
Realtime Sync
     +
Future addressable LEDs
```
