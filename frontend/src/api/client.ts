/**
 * Cliente HTTP del backend.
 *
 * La base es relativa a proposito: el mismo bundle funciona servido por FastAPI
 * en :8000 y detras del proxy de Vite en :5173. Eso elimina la necesidad de una
 * URL de backend horneada y de CORS.
 *
 * Devuelve **tipos de dominio**, no DTOs: la traduccion vive en `dto.ts` y
 * ningun llamante vuelve a ver una clave `snake_case`.
 *
 * Reparto REST / WebSocket (regla del servidor, no una preferencia):
 * por aqui viajan los comandos deliberados —encendido, brillo y el cierre de un
 * gesto de color—, que son los unicos que el backend **persiste**. El arrastre
 * continuo va por `/ws`, que no persiste nada.
 */
import {
  toActiveScene,
  toDevice,
  toDiscoveredDevice,
  toEffect,
  toErrorCode,
  toGlobalState,
  toLightState,
  toProfile,
  toRunningEffect,
  toScene,
  toSystemInfo,
  fromColor,
  fromEffectDraft,
  fromNewDevice,
  fromProfileDraft,
  fromSceneWrite,
  type DeviceDto,
  type DiscoveredDeviceDto,
  type EffectDto,
  type EffectStatusDto,
  type GlobalStateDto,
  type LightStateDto,
  type ProfileActivationDto,
  type ProfileDto,
  type SceneDto,
  type SceneStatusDto,
} from './dto'
import type { RGBColor } from '../domain/color'
import type { Device, DiscoveredDevice, NewDevice } from '../domain/devices'
import type { Effect, EffectDraft } from '../domain/effects'
import type { ErrorCode } from '../domain/errors'
import type { LightState } from '../domain/light'
import type { Profile, ProfileDraft } from '../domain/profiles'
import type { Scene, SceneWrite } from '../domain/scenes'
import type { ActiveScene, GlobalState, RunningEffect } from '../domain/state'
import type { SystemInfo } from '../domain/system'

export const API_BASE_URL = '/api/v1'

/**
 * Fallo devuelto por el backend con un codigo de estado.
 *
 * Distinguirlo de un `TypeError` de red es lo que permite a la UI separar
 * "el backend contesto que no" de "el backend no contesta": son dos señales
 * distintas y se pintan por separado.
 */
export class ApiError extends Error {
  readonly status: number
  /** Codigo estable del catalogo del backend, o `null` si el cuerpo no lo trae. */
  readonly code: ErrorCode | null

  constructor(status: number, message: string, code: ErrorCode | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export interface HealthStatus {
  status: string
}

/**
 * Una peticion que ya fallo si tenia que fallar.
 *
 * Separado de `request` porque hay dos formas de exito —con cuerpo y `204 No
 * Content`— pero **una sola politica de error**, y duplicarla dejaria que una
 * de las dos dejara de leer el codigo estable del cuerpo.
 */
async function send(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: 'application/json' },
    ...init,
  })

  if (!response.ok) {
    throw new ApiError(
      response.status,
      `${init?.method ?? 'GET'} ${path} -> ${response.status}`,
      toErrorCode(await readBody(response)),
    )
  }

  return response
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T
}

/** Exito sin cuerpo (`204`): un `json()` sobre un 204 lanzaria. */
async function requestEmpty(path: string, init: RequestInit): Promise<void> {
  await send(path, init)
}

/** Un cuerpo de error ilegible no debe tapar el codigo de estado, que si sirve. */
async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function mutation(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const apiClient = {
  /** Sonda de alcanzabilidad del backend. No toca el dispositivo. */
  getHealth: (): Promise<HealthStatus> => request<HealthStatus>('/health'),

  /**
   * Con que adaptador arranco el servidor y si puede descubrir hardware.
   *
   * Devuelve `null` —«no lo se»— cuando el cuerpo no tiene la forma esperada,
   * en vez de inventarse un valor: de esto depende que se deshabilite el boton
   * de buscar, y equivocarse en cualquiera de los dos sentidos es peor que
   * admitir que no se sabe. Un backend anterior a esta ruta responde 404 y
   * lanza `ApiError`, que el llamante trata igual: sin afirmar nada.
   */
  getSystemInfo: async (): Promise<SystemInfo | null> =>
    toSystemInfo(await request<unknown>('/system')),

  listDevices: async (): Promise<Device[]> =>
    (await request<DeviceDto[]>('/devices')).map(toDevice),

  /**
   * Escaneo BLE. **Bloquea hasta que el servidor termina** (unos segundos): la
   * peticion no vuelve antes, asi que quien la llame debe enseñar progreso.
   *
   * `timeoutSeconds` es una peticion, no una garantia: el servidor la recorta a
   * su propio limite. Si se omite, manda el valor por defecto del servidor y
   * aqui no se inventa ninguno.
   */
  scanDevices: async (timeoutSeconds?: number): Promise<DiscoveredDevice[]> => {
    const query = timeoutSeconds === undefined ? '' : `?timeout=${String(timeoutSeconds)}`
    return (await request<DiscoveredDeviceDto[]>(`/devices/scan${query}`)).map(toDiscoveredDevice)
  },

  /** Alta idempotente por direccion: repetirla devuelve el mismo `id`, no un 409. */
  registerDevice: async (device: NewDevice): Promise<Device> =>
    toDevice(await request<DeviceDto>('/devices', mutation('POST', fromNewDevice(device)))),

  connectDevice: async (deviceId: string): Promise<Device> =>
    toDevice(await request<DeviceDto>(`/devices/${deviceId}/connect`, { method: 'POST' })),

  /** Idempotente en el servidor: desconectar lo ya desconectado responde 200. */
  disconnectDevice: async (deviceId: string): Promise<Device> =>
    toDevice(await request<DeviceDto>(`/devices/${deviceId}/disconnect`, { method: 'POST' })),

  /** Hidratacion inicial: mismo cuerpo que el frame `state.snapshot`. */
  getState: async (): Promise<GlobalState> => toGlobalState(await request<GlobalStateDto>('/state')),

  setPower: async (on: boolean): Promise<LightState> =>
    toLightState(await request<LightStateDto>('/lights/power', mutation('POST', { on }))),

  setColor: async (color: RGBColor): Promise<LightState> =>
    toLightState(await request<LightStateDto>('/lights/color', mutation('PUT', fromColor(color)))),

  setBrightness: async (brightness: number): Promise<LightState> =>
    toLightState(
      await request<LightStateDto>('/lights/brightness', mutation('PUT', { brightness })),
    ),

  /** Catalogo completo, ya ordenado por nombre en el servidor. */
  listEffects: async (): Promise<Effect[]> =>
    (await request<EffectDto[]>('/effects')).map(toEffect),

  /**
   * Un efecto concreto.
   *
   * Se relee antes de editar: el catalogo **no viaja por el WebSocket**, asi que
   * la copia de la lista puede ser de hace minutos, y `PUT` es un reemplazo
   * completo. Editar sobre una copia rancia borraria en silencio lo que otro
   * cliente acabara de cambiar.
   */
  getEffect: async (effectId: string): Promise<Effect> =>
    toEffect(await request<EffectDto>(`/effects/${effectId}`)),

  /** El `id` lo genera el SERVIDOR; el cuerpo no lo lleva. */
  createEffect: async (draft: EffectDraft): Promise<Effect> =>
    toEffect(await request<EffectDto>('/effects', mutation('POST', fromEffectDraft(draft)))),

  /** Reemplazo COMPLETO, pasos incluidos. 404 si el efecto ya no existe. */
  replaceEffect: async (effectId: string, draft: EffectDraft): Promise<Effect> =>
    toEffect(
      await request<EffectDto>(`/effects/${effectId}`, mutation('PUT', fromEffectDraft(draft))),
    ),

  deleteEffect: async (effectId: string): Promise<void> => {
    await requestEmpty(`/effects/${effectId}`, { method: 'DELETE' })
  },

  /**
   * Reproduce el efecto. Sustituye al que estuviera sonando.
   *
   * El estado que devuelve tambien llega por `/ws` (`effect.started`), que es
   * quien manda: aqui se devuelve porque la respuesta prueba que el servidor
   * acepto, y quien llama puede querer saberlo sin esperar al socket.
   */
  startEffect: async (effectId: string): Promise<RunningEffect | null> =>
    toRunningEffect(
      await request<EffectStatusDto>(`/effects/${effectId}/start`, { method: 'POST' }),
    ),

  /**
   * Detiene el efecto indicado. **Idempotente.**
   *
   * Devuelve lo que suena DESPUES de la llamada, no siempre `null`: parar por id
   * un efecto al que ya sustituyo otro no para nada.
   */
  stopEffect: async (effectId: string): Promise<RunningEffect | null> =>
    toRunningEffect(
      await request<EffectStatusDto | null>(`/effects/${effectId}/stop`, { method: 'POST' }),
    ),

  /** Catalogo completo, ya ordenado por nombre en el servidor. */
  listScenes: async (): Promise<Scene[]> => (await request<SceneDto[]>('/scenes')).map(toScene),

  /**
   * Una escena concreta.
   *
   * Se relee antes de editar o de marcar favorita por el mismo motivo que los
   * efectos: el catalogo **no viaja por el WebSocket** y `PUT` es un reemplazo
   * completo, asi que escribir sobre una copia rancia borraria en silencio lo
   * que otro cliente acabara de cambiar.
   */
  getScene: async (sceneId: string): Promise<Scene> =>
    toScene(await request<SceneDto>(`/scenes/${sceneId}`)),

  /**
   * El `id` lo genera el SERVIDOR; el cuerpo no lo lleva.
   *
   * Los objetivos referencian efectos que **ya existen**: crear la escena de un
   * color fijo son dos llamadas (primero `createEffect` con un `STATIC` de un
   * paso), y quien las encadena es la capa de aplicacion, no esta.
   */
  createScene: async (scene: SceneWrite): Promise<Scene> =>
    toScene(await request<SceneDto>('/scenes', mutation('POST', fromSceneWrite(scene)))),

  /** Reemplazo COMPLETO, objetivos incluidos. 404 si la escena ya no existe. */
  replaceScene: async (sceneId: string, scene: SceneWrite): Promise<Scene> =>
    toScene(await request<SceneDto>(`/scenes/${sceneId}`, mutation('PUT', fromSceneWrite(scene)))),

  /**
   * Copia con identidad nueva.
   *
   * Sin `name`, el servidor añade su sufijo de copia; darlo evita el
   * duplicar-y-renombrar en dos peticiones. El cuerpo se omite entero cuando no
   * hay nombre: el contrato lo declara opcional y mandar `{"name": null}` seria
   * pedir explicitamente un nombre vacio.
   */
  duplicateScene: async (sceneId: string, name?: string): Promise<Scene> =>
    toScene(
      await request<SceneDto>(
        `/scenes/${sceneId}/duplicate`,
        name === undefined ? { method: 'POST' } : mutation('POST', { name }),
      ),
    ),

  deleteScene: async (sceneId: string): Promise<void> => {
    await requestEmpty(`/scenes/${sceneId}`, { method: 'DELETE' })
  },

  /**
   * Activa la escena entera. **O toda, o nada.**
   *
   * El servidor valida todos los objetivos ANTES de escribir en el dispositivo:
   * un 409 significa que no se reprodujo nada, nunca que se activo la mitad.
   * Devuelve la escena que quedo puesta; el estado autoritativo llega ademas
   * por `/ws` (`scene.activated`), que es quien manda.
   */
  activateScene: async (sceneId: string): Promise<ActiveScene | null> =>
    toActiveScene(await request<SceneStatusDto>(`/scenes/${sceneId}/activate`, { method: 'POST' })),

  listProfiles: async (): Promise<Profile[]> =>
    (await request<ProfileDto[]>('/profiles')).map(toProfile),

  getProfile: async (profileId: string): Promise<Profile> =>
    toProfile(await request<ProfileDto>(`/profiles/${profileId}`)),

  createProfile: async (draft: ProfileDraft): Promise<Profile> =>
    toProfile(await request<ProfileDto>('/profiles', mutation('POST', fromProfileDraft(draft)))),

  /** Reemplazo COMPLETO, escenas incluidas. 404 si el perfil ya no existe. */
  replaceProfile: async (profileId: string, draft: ProfileDraft): Promise<Profile> =>
    toProfile(
      await request<ProfileDto>(`/profiles/${profileId}`, mutation('PUT', fromProfileDraft(draft))),
    ),

  /** Borra el perfil y sus enlaces. Las escenas se conservan: son catalogo. */
  deleteProfile: async (profileId: string): Promise<void> => {
    await requestEmpty(`/profiles/${profileId}`, { method: 'DELETE' })
  },

  /**
   * Activa la escena predeterminada del perfil.
   *
   * Es la MISMA operacion que activar esa escena, asi que hereda todos sus
   * errores. Devuelve la escena que quedo puesta porque el perfil resuelve cual
   * es y el cliente no tiene por que repetir esa resolucion.
   */
  activateProfile: async (profileId: string): Promise<ActiveScene | null> => {
    const activation = await request<ProfileActivationDto>(`/profiles/${profileId}/activate`, {
      method: 'POST',
    })
    return toActiveScene(activation.scene)
  },
}
