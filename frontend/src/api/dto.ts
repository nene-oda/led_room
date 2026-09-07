/**
 * Frontera entre el cable y el dominio del cliente.
 *
 * El backend habla `snake_case` y publica el color como `#RRGGBB` en las
 * lecturas y como `{r,g,b}` en las mutaciones (ARCHITECTURE.md 3.2 y 3.4). El
 * dominio del cliente habla camelCase y un unico `RGBColor`.
 *
 * **Este modulo es el unico sitio donde conviven las dos formas.** Ningun
 * componente ve una clave cruda de la API: si el backend renombra
 * `white_channel`, se cambia aqui y en ningun otro lugar.
 *
 * Los tipos `*Dto` describen lo que llega por el cable, no lo que la UI usa.
 * Son estructuras de transporte y por eso conservan su forma original, incluida
 * la tolerancia a claves ausentes: Pydantic las serializa con `null`, pero un
 * DTO que asume su presencia se rompe en cuanto alguien añade un `exclude_none`.
 */
import { fromHex, toHex, type RGBColor } from '../domain/color'
import {
  type Device,
  type DeviceCapabilities,
  type DeviceLink,
  type DiscoveredDevice,
  type NewDevice,
} from '../domain/devices'
import { SCAN_TIMEOUT_SECONDS } from '../domain/discovery'
import {
  isEasing,
  isEffectType,
  type Effect,
  type EffectDraft,
  type EffectStep,
} from '../domain/effects'
import { isErrorCode, type ErrorCode } from '../domain/errors'
import { clampBrightness, type LightState } from '../domain/light'
import type { Profile, ProfileDraft, ProfileScene } from '../domain/profiles'
import type { Scene, SceneTarget, SceneWrite } from '../domain/scenes'
import type { ActiveScene, GlobalState, RunningEffect } from '../domain/state'
import type { SystemInfo } from '../domain/system'

// ---------------------------------------------------------------------------
// Lo que llega por el cable
// ---------------------------------------------------------------------------

export interface ColorDto {
  r: number
  g: number
  b: number
}

export interface LightStateDto {
  power: boolean
  /** `#RRGGBB` en MAYUSCULAS. */
  color: string
  brightness: number
}

export interface DeviceLinkDto {
  device_id: string
  connected: boolean
  rssi?: number | null
  last_error?: string | null
}

export interface DeviceCapabilitiesDto {
  rgb: boolean
  brightness: boolean
  effects: boolean
  addressable: boolean
  segments: boolean
  white_channel: boolean
  music_mode: boolean
}

export interface DeviceDto {
  id: string
  name: string
  adapter_type: string
  address?: string | null
  enabled: boolean
  auto_connect: boolean
  connected: boolean
  capabilities: DeviceCapabilitiesDto
}

/** Resultado de `GET /devices/scan`. Un anuncio BLE, no un dispositivo dado de alta. */
export interface DiscoveredDeviceDto {
  name?: string | null
  address: string
  rssi?: number | null
}

/**
 * Cuerpo de `POST /devices`.
 *
 * `adapter_type` se omite a proposito para que el servidor aplique el suyo: es
 * el unico que sabe con que adaptador arranco.
 */
export interface NewDeviceDto {
  name?: string
  address: string
}

/** Efecto en curso. El campo entero es `null` cuando no suena nada. */
export interface EffectStatusDto {
  running: boolean
  id: string
}

/** Escena activa. El campo entero es `null` cuando el servidor no da ninguna. */
export interface SceneStatusDto {
  id: string
}

export interface GlobalStateDto {
  version: number
  device?: DeviceLinkDto | null
  light: LightStateDto
  effect?: EffectStatusDto | null
  scene?: SceneStatusDto | null
}

/** Un paso tal y como se publica. El color va en `#RRGGBB` MAYUSCULAS. */
export interface EffectStepDto {
  position: number
  color: string
  brightness?: number | null
  duration_ms?: number | null
  easing?: string | null
}

export interface EffectDto {
  id: string
  name: string
  type: string
  description?: string | null
  loop: boolean
  speed: number
  fps: number
  transition_ms: number
  min_brightness: number
  max_brightness: number
  is_builtin: boolean
  steps: EffectStepDto[]
}

/**
 * Cuerpo de `POST /effects` y de `PUT /effects/{id}`.
 *
 * Sin `id` ni `is_builtin`: los decide el servidor. Y sin `position` en los
 * pasos, porque **la posicion es el indice del array** (contrato de escritura,
 * backend/app/api/schemas/effects.py).
 */
export interface EffectStepWriteDto {
  color: string
  brightness: number | null
  duration_ms: number | null
  easing: string | null
}

export interface EffectWriteDto {
  name: string
  type: string
  description: string | null
  loop: boolean
  speed: number
  fps: number
  transition_ms: number
  min_brightness: number
  max_brightness: number
  steps: EffectStepWriteDto[]
}

export interface SceneTargetDto {
  device_id: string
  effect_id: string
  brightness?: number | null
  speed?: number | null
  enabled: boolean
}

export interface SceneDto {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  is_builtin: boolean
  is_favorite: boolean
  targets: SceneTargetDto[]
}

/**
 * Cuerpo de `POST /scenes` y de `PUT /scenes/{id}`.
 *
 * Sin `id` ni `is_builtin`: los decide el servidor. Cada objetivo referencia un
 * `effect_id` que **ya existe**; el contrato no acepta un efecto incrustado
 * (backend/app/api/schemas/scenes.py).
 */
export interface SceneTargetWriteDto {
  device_id: string
  effect_id: string
  brightness: number | null
  speed: number | null
  enabled: boolean
}

export interface SceneWriteDto {
  name: string
  description: string | null
  icon: string | null
  is_favorite: boolean
  targets: SceneTargetWriteDto[]
}

export interface ProfileSceneDto {
  scene_id: string
  position: number
  is_default: boolean
}

export interface ProfileDto {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  is_builtin: boolean
  scenes: ProfileSceneDto[]
  /** Ya resuelto por el servidor: el cliente no reimplementa el desempate. */
  default_scene_id?: string | null
}

/** Cuerpo de `POST /profiles` y de `PUT /profiles/{id}`. Sin `position`. */
export interface ProfileSceneWriteDto {
  scene_id: string
  is_default: boolean
}

export interface ProfileWriteDto {
  name: string
  description: string | null
  icon: string | null
  scenes: ProfileSceneWriteDto[]
}

/** Resultado de `POST /profiles/{id}/activate`: que escena quedo puesta. */
export interface ProfileActivationDto {
  profile_id: string
  scene: SceneStatusDto
}

/**
 * Cuerpo de `GET /system`: con que adaptador arranco el servidor.
 *
 * **Es el unico sitio del cliente que conoce la forma de esta respuesta.** Si
 * el backend mueve la ruta o renombra una clave, se ajusta `toSystemInfo` y no
 * hay que tocar nada mas de la UI.
 */
export interface SystemInfoDto {
  adapter_type: string
  supports_discovery: boolean
  scan_timeout_seconds: number
}

// ---------------------------------------------------------------------------
// Cable -> dominio
// ---------------------------------------------------------------------------

export function toCapabilities(dto: DeviceCapabilitiesDto): DeviceCapabilities {
  return {
    rgb: dto.rgb,
    brightness: dto.brightness,
    effects: dto.effects,
    addressable: dto.addressable,
    segments: dto.segments,
    whiteChannel: dto.white_channel,
    musicMode: dto.music_mode,
  }
}

export function toDevice(dto: DeviceDto): Device {
  return {
    id: dto.id,
    name: dto.name,
    adapterType: dto.adapter_type,
    address: dto.address ?? null,
    enabled: dto.enabled,
    autoConnect: dto.auto_connect,
    connected: dto.connected,
    capabilities: toCapabilities(dto.capabilities),
  }
}

export function toDiscoveredDevice(dto: DiscoveredDeviceDto): DiscoveredDevice {
  return {
    name: dto.name ?? null,
    address: dto.address,
    rssi: dto.rssi ?? null,
  }
}

/**
 * `GET /system` -> dominio, o `null` si la respuesta no es la que esperamos.
 *
 * Valida en vez de confiar, y **degrada a «no lo se» en vez de fallar**, porque
 * de este valor depende que se deshabilite un boton: creerse un cuerpo raro
 * podria dejar el descubrimiento apagado en un servidor que si tiene radio, o
 * prometerlo en uno que no la tiene. Cuando la forma no encaja, la UI se queda
 * exactamente como estaba antes de existir este endpoint: sin afirmar nada.
 *
 * Lo unico imprescindible es `supports_discovery`, que es el hecho por el que
 * se pregunta. Lo demas tiene respaldo: el nombre del adaptador solo se enseña
 * y el timeout tiene su valor por defecto en el dominio.
 */
export function toSystemInfo(body: unknown): SystemInfo | null {
  if (!isRecord(body)) return null

  const supports = body['supports_discovery']
  if (typeof supports !== 'boolean') return null

  const adapter = body['adapter_type']
  const timeout = body['scan_timeout_seconds']

  return {
    adapterType: typeof adapter === 'string' && adapter !== '' ? adapter : null,
    supportsDiscovery: supports,
    scanTimeoutSeconds:
      typeof timeout === 'number' && Number.isFinite(timeout) && timeout > 0
        ? timeout
        : SCAN_TIMEOUT_SECONDS,
  }
}

export function toLightState(dto: LightStateDto): LightState {
  // `fromHex` lanza RangeError si el servidor enviara algo que no es #RRGGBB:
  // preferimos el fallo ruidoso a pintar un color inventado.
  return {
    power: dto.power,
    color: fromHex(dto.color),
    brightness: clampBrightness(dto.brightness),
  }
}

export function toDeviceLink(dto: DeviceLinkDto): DeviceLink {
  return {
    deviceId: dto.device_id,
    connected: dto.connected,
    rssi: dto.rssi ?? null,
    lastError: dto.last_error ?? null,
  }
}

/**
 * `{running, id}` -> id, o `null`.
 *
 * Un `running: false` se trata como "no suena nada": el servidor solo publica
 * el campo mientras hay reproduccion, asi que un `false` solo podria venir de un
 * backend que cambiara el contrato, y creerselo dejaria la UI diciendo que hay
 * un efecto en marcha que nadie esta reproduciendo.
 */
export function toRunningEffect(dto: EffectStatusDto | null | undefined): RunningEffect | null {
  return dto == null || !dto.running ? null : { id: dto.id }
}

/**
 * `{id}` -> escena activa, o `null`.
 *
 * **Se copia tal cual, sin deducir nada.** La ranura la escribe solo el
 * servidor; vaciarla aqui porque el efecto dejo de sonar mentiria con las
 * escenas de color fijo, cuyo efecto `STATIC` termina y dejan la tira puesta.
 */
export function toActiveScene(dto: SceneStatusDto | null | undefined): ActiveScene | null {
  return dto == null ? null : { id: dto.id }
}

export function toGlobalState(dto: GlobalStateDto): GlobalState {
  return {
    version: dto.version,
    device: dto.device == null ? null : toDeviceLink(dto.device),
    light: toLightState(dto.light),
    effect: toRunningEffect(dto.effect),
    scene: toActiveScene(dto.scene),
  }
}

function toSceneTarget(dto: SceneTargetDto): SceneTarget {
  return {
    deviceId: dto.device_id,
    effectId: dto.effect_id,
    brightness: dto.brightness ?? null,
    speed: dto.speed ?? null,
    enabled: dto.enabled,
  }
}

export function toScene(dto: SceneDto): Scene {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    icon: dto.icon ?? null,
    isBuiltin: dto.is_builtin,
    isFavorite: dto.is_favorite,
    targets: dto.targets.map(toSceneTarget),
  }
}

function toProfileScene(dto: ProfileSceneDto): ProfileScene {
  return { sceneId: dto.scene_id, position: dto.position, isDefault: dto.is_default }
}

export function toProfile(dto: ProfileDto): Profile {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description ?? null,
    icon: dto.icon ?? null,
    isBuiltin: dto.is_builtin,
    scenes: dto.scenes.map(toProfileScene),
    defaultSceneId: dto.default_scene_id ?? null,
  }
}

function toEffectStep(dto: EffectStepDto): EffectStep {
  return {
    color: fromHex(dto.color),
    brightness: dto.brightness ?? null,
    durationMs: dto.duration_ms ?? null,
    easing: isEasing(dto.easing) ? dto.easing : null,
  }
}

/**
 * Un efecto del catalogo.
 *
 * El `type` se valida contra el catalogo congelado y **se falla ruidosamente**
 * si no encaja, igual que hace `toLightState` con un color mal formado: pintar
 * un efecto cuyo algoritmo no conocemos seria enseñar cotas de paleta
 * inventadas.
 */
export function toEffect(dto: EffectDto): Effect {
  if (!isEffectType(dto.type)) {
    throw new RangeError(`Tipo de efecto desconocido: ${JSON.stringify(dto.type)}`)
  }

  return {
    id: dto.id,
    name: dto.name,
    type: dto.type,
    description: dto.description ?? null,
    loop: dto.loop,
    speed: dto.speed,
    fps: dto.fps,
    transitionMs: dto.transition_ms,
    minBrightness: dto.min_brightness,
    maxBrightness: dto.max_brightness,
    isBuiltin: dto.is_builtin,
    // El orden del array ES la posicion: el contrato de escritura no acepta
    // otra cosa, asi que conservar `position` permitiria dos ordenes distintos.
    steps: dto.steps.map(toEffectStep),
  }
}

// ---------------------------------------------------------------------------
// Dominio -> cable
// ---------------------------------------------------------------------------

/**
 * Cuerpo de `POST /devices`.
 *
 * La clave `name` se **omite** cuando el anuncio BLE no traia ninguno, en vez
 * de mandar `null`: asi el servidor aplica su nombre por defecto en lugar de
 * guardar un dispositivo sin nombre que luego no se puede distinguir en la
 * lista.
 */
export function fromNewDevice(device: NewDevice): NewDeviceDto {
  return device.name === null
    ? { address: device.address }
    : { name: device.name, address: device.address }
}

/** Cuerpo de `PUT /lights/color` y payload del comando `light.color`. */
export function fromColor(color: RGBColor): ColorDto {
  return { r: color.r, g: color.g, b: color.b }
}

/**
 * Cuerpo de `POST /effects` y de `PUT /effects/{id}`.
 *
 * El nombre se recorta aqui y no en el editor: un nombre con espacios al final
 * pasaria el `min_length=1` del servidor y quedaria guardado con ellos.
 */
export function fromEffectDraft(draft: EffectDraft): EffectWriteDto {
  return {
    name: draft.name.trim(),
    type: draft.type,
    description: draft.description,
    loop: draft.loop,
    speed: draft.speed,
    fps: draft.fps,
    transition_ms: draft.transitionMs,
    min_brightness: draft.minBrightness,
    max_brightness: draft.maxBrightness,
    steps: draft.steps.map((step) => ({
      color: toHex(step.color),
      brightness: step.brightness,
      duration_ms: step.durationMs,
      easing: step.easing,
    })),
  }
}

/**
 * Cuerpo de `POST /scenes` y de `PUT /scenes/{id}`.
 *
 * El nombre se recorta aqui por el mismo motivo que en `fromEffectDraft`: un
 * nombre con espacios al final pasaria el `min_length=1` del servidor y
 * quedaria guardado con ellos.
 */
export function fromSceneWrite(scene: SceneWrite): SceneWriteDto {
  return {
    name: scene.name.trim(),
    description: scene.description,
    icon: scene.icon,
    is_favorite: scene.isFavorite,
    targets: scene.targets.map((target) => ({
      device_id: target.deviceId,
      effect_id: target.effectId,
      brightness: target.brightness,
      speed: target.speed,
      enabled: target.enabled,
    })),
  }
}

/** Cuerpo de `POST /profiles` y de `PUT /profiles/{id}`. */
export function fromProfileDraft(draft: ProfileDraft): ProfileWriteDto {
  return {
    name: draft.name.trim(),
    description: draft.description,
    icon: draft.icon,
    // Sin `position`: **es el indice del array** (contrato de escritura,
    // backend/app/api/schemas/profiles.py).
    scenes: draft.scenes.map((link) => ({ scene_id: link.sceneId, is_default: link.isDefault })),
  }
}

// ---------------------------------------------------------------------------
// Cuerpo de error
// ---------------------------------------------------------------------------

/**
 * Extrae el codigo estable de `{"detail": {"code", "message"}}`.
 *
 * Devuelve `null` cuando el cuerpo no tiene esa forma, que es el caso de los
 * 404 de rutas inexistentes: FastAPI los deja con su cuerpo por defecto y darles
 * un codigo obligaria a inventar uno que no esta en el catalogo.
 */
export function toErrorCode(body: unknown): ErrorCode | null {
  if (!isRecord(body)) return null
  const detail = body['detail']
  if (!isRecord(detail)) return null
  return isErrorCode(detail['code']) ? detail['code'] : null
}

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------

/** Comando del cliente al servidor: imperativo y sin sufijo (README 17). */
export type ClientCommand =
  | { readonly type: 'light.power'; readonly payload: { readonly on: boolean } }
  | { readonly type: 'light.color'; readonly payload: ColorDto }
  | { readonly type: 'light.brightness'; readonly payload: { readonly brightness: number } }

export function powerCommand(on: boolean): ClientCommand {
  return { type: 'light.power', payload: { on } }
}

export function colorCommand(color: RGBColor): ClientCommand {
  return { type: 'light.color', payload: fromColor(color) }
}

export function brightnessCommand(brightness: number): ClientCommand {
  return { type: 'light.brightness', payload: { brightness: clampBrightness(brightness) } }
}

/**
 * Contenido de un evento del servidor, ya traducido a dominio.
 *
 * `scene.activated` describe la ranura de escena del estado global, igual que
 * `effect.*` describe la de efecto. El servidor lo publica DESPUES del
 * `effect.started` de la escena, asi que su version siempre es mayor y el
 * filtro por version no lo descarta.
 *
 * `effect.started` y `effect.stopped` comparten un solo `kind`: describen el
 * mismo campo del estado global (la ranura de efecto) y separarlos obligaria a
 * repetir en dos ramas del reductor la misma escritura.
 */
export type ServerEventBody =
  | { readonly kind: 'snapshot'; readonly state: GlobalState }
  | { readonly kind: 'power'; readonly power: boolean }
  | { readonly kind: 'color'; readonly color: RGBColor }
  | { readonly kind: 'brightness'; readonly brightness: number }
  | { readonly kind: 'device'; readonly deviceId: string; readonly connected: boolean }
  | { readonly kind: 'effect'; readonly effectId: string; readonly running: boolean }
  | { readonly kind: 'scene'; readonly sceneId: string }
  | { readonly kind: 'error'; readonly code: ErrorCode; readonly message: string }

/**
 * Un frame servidor -> cliente completo: contenido + version del sobre.
 *
 * `version` viaja en TODOS los frames (`{type, version, payload}`) y es
 * estrictamente creciente dentro de una sesion del servidor. El cliente la usa
 * para dos cosas que no puede resolver de otra forma:
 *
 *   - **descartar frames rancios**: un `state.snapshot` que llegue despues de un
 *     evento mas nuevo dejaria la pantalla congelada en un estado viejo de forma
 *     permanente;
 *   - **detectar huecos**: si la version salta, se perdieron eventos y hay que
 *     volver a pedir `GET /api/v1/state`.
 *
 * Se admite `null` porque un backend anterior a la correccion del sobre no la
 * envia. En ese caso el frame se aplica sin comprobacion, que es exactamente el
 * comportamiento de antes.
 */
export type ServerEvent = ServerEventBody & { readonly version: number | null }

/**
 * Decodifica un frame `{type, payload}` del WebSocket.
 *
 * Devuelve `null` para los frames que este cliente ignora y para los que no
 * entiende. Un frame ilegible del propio backend es un fallo del contrato, no
 * un caso normal: se registra en consola para que quede a la vista, pero no
 * tumba la conexion ni la pantalla.
 */
export function parseServerEvent(raw: string): ServerEvent | null {
  try {
    const frame: unknown = JSON.parse(raw)
    if (!isRecord(frame)) return null

    const payload = isRecord(frame['payload']) ? frame['payload'] : {}
    const body = decode(frame['type'], payload)
    if (body === null) return null

    const version = frame['version']
    return { ...body, version: typeof version === 'number' ? version : null }
  } catch (error) {
    console.warn('Frame de WebSocket ilegible', raw, error)
    return null
  }
}

function decode(type: unknown, payload: Record<string, unknown>): ServerEventBody | null {
  switch (type) {
    case 'state.snapshot':
      return { kind: 'snapshot', state: toGlobalState(payload as unknown as GlobalStateDto) }
    case 'light.power.changed':
      return { kind: 'power', power: Boolean(payload['power']) }
    case 'light.color.changed':
      return { kind: 'color', color: fromHex(String(payload['color'])) }
    case 'light.brightness.changed':
      return { kind: 'brightness', brightness: clampBrightness(Number(payload['brightness'])) }
    case 'device.connected':
      return { kind: 'device', deviceId: String(payload['device_id']), connected: true }
    case 'device.disconnected':
      return { kind: 'device', deviceId: String(payload['device_id']), connected: false }
    case 'effect.started':
      return { kind: 'effect', effectId: String(payload['effect_id']), running: true }
    case 'effect.stopped':
      return { kind: 'effect', effectId: String(payload['effect_id']), running: false }
    case 'scene.activated':
      return { kind: 'scene', sceneId: String(payload['scene_id']) }
    case 'error':
      return {
        kind: 'error',
        code: isErrorCode(payload['code']) ? payload['code'] : 'internal_error',
        message: String(payload['message'] ?? ''),
      }
    default:
      // Cualquier evento futuro que esta version no pinte: ignorado a proposito.
      return null
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
