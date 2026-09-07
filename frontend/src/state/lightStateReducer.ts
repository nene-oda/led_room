/**
 * Reconciliacion entre el estado autoritativo del servidor y lo que el usuario
 * esta tocando ahora mismo. **Funcion pura**: ni React, ni red, ni temporizadores.
 *
 * Cuatro reglas, y las cuatro tienen un motivo concreto:
 *
 * 1. **El backend manda.** `server` solo cambia con lo que dice el servidor
 *    (snapshot, evento o respuesta REST). Nunca con lo que el usuario desea.
 * 2. **Optimismo acotado.** `local` guarda el valor que el usuario acaba de
 *    elegir para que el control responda al instante. Se retira en cuanto llega
 *    la verdad.
 * 3. **Supresion de eco.** Mientras hay un gesto vivo sobre un campo, los
 *    eventos del servidor para *ese* campo actualizan `server` pero **no**
 *    retiran el valor local. Sin esto el slider pelea contra su propio eco
 *    (el servidor difunde a todos los clientes, incluido el emisor) y da
 *    tirones al arrastrar.
 * 4. **Rollback explicito y visible.** Si la mutacion falla, el valor local se
 *    descarta —vuelve a verse el del servidor— y se produce un aviso. Un fallo
 *    silencioso deja la pantalla mintiendo.
 *
 * Fuera de un gesto, el evento del servidor gana siempre sobre el optimista.
 *
 * A esas cuatro se suma el **orden**: todos los frames del servidor llevan
 * `version` en el sobre y es estrictamente creciente dentro de una sesion. Un
 * frame con version menor o igual a la ya aplicada se descarta —protege de la
 * carrera en la que un `state.snapshot` llega despues de un evento mas nuevo y
 * dejaria la pantalla rancia para siempre— y un salto de version se marca como
 * hueco para volver a pedir `GET /state`. Al caerse el socket la version deja
 * de ser comparable (el servidor puede haber reiniciado y volver a contar desde
 * cero), asi que se olvida: eso es `session-reset`.
 */
import { rgb, type RGBColor } from '../domain/color'
import { NO_CAPABILITIES, type Device, type DeviceCapabilities, type DeviceLink } from '../domain/devices'
import { describeErrorCode } from '../domain/errors'
import type { BackendStatus } from '../domain/connection'
import type { LightState } from '../domain/light'
import type { ActiveScene, GlobalState, RunningEffect } from '../domain/state'
import type { SystemInfo } from '../domain/system'
import type { ServerEvent } from '../api/dto'

/** Los tres campos que el usuario puede mutar hoy. */
export type LightField = 'power' | 'color' | 'brightness'

export interface LocalOverrides {
  readonly power: boolean | null
  readonly color: RGBColor | null
  readonly brightness: number | null
}

export type GestureFlags = Readonly<Record<LightField, boolean>>

export interface Notice {
  readonly message: string
}

export interface LightUiState {
  readonly hydration: 'loading' | 'ready' | 'failed'
  readonly backend: BackendStatus
  /** Version aplicada, o `UNKNOWN_VERSION` mientras no haya base comparable. */
  readonly version: number
  /** Ultimo estado conocido del servidor. */
  readonly server: LightState
  readonly link: DeviceLink | null
  readonly devices: readonly Device[]
  /**
   * Con que adaptador arranco el servidor, o `null` mientras no lo haya dicho.
   *
   * Vive aqui —y no en el hook de descubrimiento— porque **no es estado de una
   * tarea**: lo miran la tarjeta de conexion y la de dispositivos, y pedirlo
   * dos veces daria dos copias que pueden discrepar. Es lo mismo que se hace
   * con `devices`: una lectura, un titular.
   */
  readonly system: SystemInfo | null
  readonly local: LocalOverrides
  readonly gestures: GestureFlags
  readonly linkPending: boolean
  /** Se detecto un hueco de versiones: hay que volver a hidratar por REST. */
  readonly resyncRequested: boolean
  readonly notice: Notice | null
  /** Efecto que el servidor esta reproduciendo, o `null`. */
  readonly effect: RunningEffect | null
  /**
   * Efecto sobre el que el usuario ya lanzo un comando manual y que, por tanto,
   * el servidor va a detener. Es una **expectativa**, no un hecho: se confirma
   * cuando llega el `effect.stopped` correspondiente.
   */
  readonly preemptedEffectId: string | null
  /**
   * Efecto que un comando manual **acaba de detener**, ya confirmado.
   *
   * Existe para poder decirlo en pantalla. Que un comando manual cancele el
   * efecto es comportamiento del servidor (`LightService` precede cada mutacion
   * con `EffectPlayer.stop`), y ocultarlo dejaria al usuario preguntandose por
   * que se apago el efecto justo al mover el color.
   */
  readonly effectStoppedByCommand: string | null
  /**
   * Escena que el SERVIDOR da por activa.
   *
   * Se escribe con el snapshot y con `scene.activated`, y con nada mas. En
   * concreto **no se vacia** cuando para el efecto: quien decide cuando una
   * escena deja de estar puesta es el servidor, y deducirlo aqui mentiria con
   * las escenas de color fijo —su efecto `STATIC` termina y la tira sigue como
   * la escena la dejo— y con los efectos sueltos, que no son escena de nadie.
   */
  readonly scene: ActiveScene | null
}

/**
 * "No hay ninguna version aplicada todavia".
 *
 * No es 0: el servidor empieza en 0 y confundirlos haria que el primer frame de
 * una sesion nueva se descartara por rancio.
 */
export const UNKNOWN_VERSION = -1

/**
 * Marcador de posicion hasta la primera hidratacion.
 *
 * No se muestra como si fuera real: mientras `hydration` sea `loading` la
 * pantalla lo dice y los controles estan deshabilitados.
 */
const PLACEHOLDER_LIGHT: LightState = { power: false, color: rgb(255, 255, 255), brightness: 100 }

export const initialLightUiState: LightUiState = {
  hydration: 'loading',
  backend: 'checking',
  version: UNKNOWN_VERSION,
  server: PLACEHOLDER_LIGHT,
  link: null,
  devices: [],
  system: null,
  local: { power: null, color: null, brightness: null },
  gestures: { power: false, color: false, brightness: false },
  linkPending: false,
  resyncRequested: false,
  notice: null,
  effect: null,
  preemptedEffectId: null,
  effectStoppedByCommand: null,
  scene: null,
}

export type LightAction =
  | {
      readonly type: 'hydrated'
      readonly state: GlobalState
      readonly devices: readonly Device[]
      /**
       * `null` o ausente si el servidor no lo publica o no se pudo leer.
       *
       * Las dos formas significan lo mismo —«no lo se»— y el reductor las trata
       * igual: conserva lo ultimo que el servidor si dijo.
       */
      readonly system?: SystemInfo | null | undefined
    }
  | {
      readonly type: 'hydration-failed'
      readonly message: string
      readonly backendReachable: boolean
    }
  | { readonly type: 'server-event'; readonly event: ServerEvent }
  | { readonly type: 'local-change'; readonly field: 'power'; readonly value: boolean }
  | { readonly type: 'local-change'; readonly field: 'color'; readonly value: RGBColor }
  | { readonly type: 'local-change'; readonly field: 'brightness'; readonly value: number }
  | {
      readonly type: 'commit-succeeded'
      readonly field: LightField
      readonly light: LightState
    }
  | {
      readonly type: 'commit-failed'
      readonly field: LightField
      readonly message: string
      readonly backendReachable: boolean
    }
  | { readonly type: 'session-reset' }
  | { readonly type: 'link-started' }
  | { readonly type: 'link-failed'; readonly message: string; readonly backendReachable: boolean }
  | { readonly type: 'notice-dismissed' }

export function lightStateReducer(state: LightUiState, action: LightAction): LightUiState {
  switch (action.type) {
    case 'hydrated': {
      // La lista de dispositivos no tiene version y siempre es util (de ahi
      // salen las capacidades). El estado de la luz, en cambio, puede ser mas
      // viejo que lo que ya llego por el socket: entonces se conserva el que
      // hay y solo se cierra el hueco.
      const fresh = isNewer(state.version, action.state.version)
      return {
        ...state,
        hydration: 'ready',
        backend: 'reachable',
        linkPending: false,
        resyncRequested: false,
        devices: action.devices,
        // Un fallo al releer `/system` no borra lo que el servidor ya dijo:
        // volver a "no lo se" reabriria un boton que sabemos que no sirve.
        system: action.system ?? state.system,
        ...(fresh
          ? {
              version: action.state.version,
              server: action.state.light,
              link: action.state.device,
              effect: action.state.effect,
              scene: action.state.scene,
              local: keepOnlyGestures(state),
            }
          : {}),
      }
    }

    case 'hydration-failed':
      return {
        ...state,
        // Un fallo al refrescar no borra lo que ya se estaba mostrando: mentiria
        // menos una pantalla vieja con el aviso a la vista que una en blanco.
        hydration: state.hydration === 'ready' ? 'ready' : 'failed',
        backend: action.backendReachable ? 'reachable' : 'unreachable',
        linkPending: false,
        // Se limpia aunque haya fallado: reintentar en bucle contra un backend
        // caido no arregla el hueco y si esconde el aviso detras de mas ruido.
        resyncRequested: false,
        notice: { message: action.message },
      }

    case 'server-event':
      return applyServerEvent(state, action.event)

    case 'local-change':
      return {
        ...state,
        local: withLocal(state.local, action),
        gestures: setFlag(state.gestures, action.field, true),
        // El servidor detiene el efecto en curso ANTES de aplicar cualquier
        // comando manual. Se anota aqui, con el gesto, y no al recibir la
        // parada: cuando llega el `effect.stopped` ya no se sabria si lo
        // provoco el usuario o si el efecto simplemente termino.
        preemptedEffectId: state.effect?.id ?? state.preemptedEffectId,
      }

    case 'commit-succeeded':
      return {
        ...state,
        backend: 'reachable',
        server: action.light,
        local: clearLocal(state.local, action.field),
        gestures: setFlag(state.gestures, action.field, false),
      }

    case 'commit-failed':
      return {
        ...state,
        backend: action.backendReachable ? 'reachable' : 'unreachable',
        local: clearLocal(state.local, action.field),
        gestures: setFlag(state.gestures, action.field, false),
        notice: { message: action.message },
      }

    case 'session-reset':
      // El socket dejo de estar abierto: la numeracion del servidor ya no es
      // comparable con la nuestra. El proximo snapshot vuelve a fijar la base.
      return { ...state, version: UNKNOWN_VERSION, resyncRequested: false }

    case 'link-started':
      return { ...state, linkPending: true, notice: null }

    case 'link-failed':
      return {
        ...state,
        linkPending: false,
        backend: action.backendReachable ? 'reachable' : 'unreachable',
        notice: { message: action.message },
      }

    case 'notice-dismissed':
      return { ...state, notice: null }
  }
}

function applyServerEvent(state: LightUiState, event: ServerEvent): LightUiState {
  // `error` no describe un estado, describe un comando rechazado: no lleva
  // orden que respetar y filtrarlo por version lo haria desaparecer.
  if (event.kind === 'error') {
    // No dice a que campo afecta, asi que no se puede revertir nada concreto:
    // se muestra. Callarlo seria el peor modo posible para un control de
    // arrastre, que es justo lo que viaja por este canal.
    return { ...state, notice: { message: describeErrorCode(event.code) } }
  }

  if (!isNewer(state.version, event.version)) return state

  const applied = applyBody(state, event)
  return {
    ...applied,
    version: event.version ?? state.version,
    resyncRequested: applied.resyncRequested || hasGap(state.version, event.version),
  }
}

/**
 * Un frame es aplicable si trae una version mayor que la aplicada, si no trae
 * version (backend anterior a la correccion del sobre) o si todavia no hay base
 * comparable.
 */
function isNewer(applied: number, incoming: number | null): boolean {
  return incoming === null || applied === UNKNOWN_VERSION || incoming > applied
}

/** Falta al menos un evento intermedio: hay que rehidratar por REST. */
function hasGap(applied: number, incoming: number | null): boolean {
  return incoming !== null && applied !== UNKNOWN_VERSION && incoming > applied + 1
}

function applyBody(state: LightUiState, event: ServerEvent): LightUiState {
  switch (event.kind) {
    case 'snapshot':
      return {
        ...state,
        hydration: 'ready',
        server: event.state.light,
        link: event.state.device,
        effect: event.state.effect,
        scene: event.state.scene,
        local: keepOnlyGestures(state),
      }

    case 'power':
      return applyServerField(state, 'power', { ...state.server, power: event.power })

    case 'color':
      return applyServerField(state, 'color', { ...state.server, color: event.color })

    case 'brightness':
      return applyServerField(state, 'brightness', {
        ...state.server,
        brightness: event.brightness,
      })

    case 'device':
      return { ...state, link: applyLink(state.link, event.deviceId, event.connected) }

    case 'effect':
      return applyEffect(state, event.effectId, event.running)

    case 'scene':
      // Misma puerta que los demas eventos: ya paso el filtro por version en
      // `applyServerEvent`, asi que aqui no hay ningun orden que rehacer.
      return { ...state, scene: { id: event.sceneId } }

    case 'error':
      // Atendido antes de llegar aqui.
      return state
  }
}

/**
 * El valor del servidor entra siempre; el optimista se retira **salvo** que
 * haya un gesto vivo sobre ese mismo campo (supresion de eco).
 */
function applyServerField(state: LightUiState, field: LightField, server: LightState): LightUiState {
  return {
    ...state,
    server,
    local: state.gestures[field] ? state.local : clearLocal(state.local, field),
  }
}

/**
 * `effect.started` / `effect.stopped`.
 *
 * La parada se ignora cuando habla de un efecto que ya no es el que consta:
 * misma regla que aplica el servidor en `EffectPlayer._clear`, porque una
 * notificacion tardia de un efecto ya sustituido apagaria el indicador del que
 * el usuario acaba de arrancar.
 */
function applyEffect(state: LightUiState, effectId: string, running: boolean): LightUiState {
  if (running) {
    // Arrancar algo nuevo cierra el episodio anterior: lo que se contaba de la
    // parada anterior ya no describe lo que se ve.
    return {
      ...state,
      effect: { id: effectId },
      preemptedEffectId: null,
      effectStoppedByCommand: null,
    }
  }

  if (state.effect !== null && state.effect.id !== effectId) return state

  const byCommand = state.preemptedEffectId === effectId
  return {
    ...state,
    effect: null,
    preemptedEffectId: null,
    effectStoppedByCommand: byCommand ? effectId : null,
  }
}

/**
 * `device.connected` / `device.disconnected` solo traen el id. El resto del
 * detalle (rssi, ultimo error) llega con el siguiente snapshot; conservar el
 * anterior seria inventarse informacion que puede haber caducado.
 */
function applyLink(link: DeviceLink | null, deviceId: string, connected: boolean): DeviceLink {
  const lastError = link !== null && link.deviceId === deviceId && !connected ? link.lastError : null
  return { deviceId, connected, rssi: null, lastError }
}

function keepOnlyGestures(state: LightUiState): LocalOverrides {
  return {
    power: state.gestures.power ? state.local.power : null,
    color: state.gestures.color ? state.local.color : null,
    brightness: state.gestures.brightness ? state.local.brightness : null,
  }
}

function withLocal(
  local: LocalOverrides,
  action: Extract<LightAction, { type: 'local-change' }>,
): LocalOverrides {
  switch (action.field) {
    case 'power':
      return { ...local, power: action.value }
    case 'color':
      return { ...local, color: action.value }
    case 'brightness':
      return { ...local, brightness: action.value }
  }
}

function clearLocal(local: LocalOverrides, field: LightField): LocalOverrides {
  return {
    power: field === 'power' ? null : local.power,
    color: field === 'color' ? null : local.color,
    brightness: field === 'brightness' ? null : local.brightness,
  }
}

function setFlag(gestures: GestureFlags, field: LightField, active: boolean): GestureFlags {
  return {
    power: field === 'power' ? active : gestures.power,
    color: field === 'color' ? active : gestures.color,
    brightness: field === 'brightness' ? active : gestures.brightness,
  }
}

// ---------------------------------------------------------------------------
// Selectores. Estado derivado, nunca duplicado.
// ---------------------------------------------------------------------------

/** Lo que se pinta: el valor local si lo hay, el del servidor si no. */
export function visibleLight(state: LightUiState): LightState {
  return {
    power: state.local.power ?? state.server.power,
    color: state.local.color ?? state.server.color,
    brightness: state.local.brightness ?? state.server.brightness,
  }
}

/**
 * El dispositivo con el que trabaja la pantalla: el del enlace si hay enlace, y
 * si no el primero registrado, que es al que ofrecer "Conectar".
 */
export function activeDevice(state: LightUiState): Device | null {
  const linkId = state.link?.deviceId
  return state.devices.find((device) => device.id === linkId) ?? state.devices[0] ?? null
}

/**
 * Capacidades vigentes.
 *
 * Sin enlace no hay capacidades: todo a `false`. Suponer lo contrario dejaria
 * controles habilitados que el servidor rechazaria con 409, y el usuario veria
 * un fallo donde deberia haber visto una explicacion.
 */
export function activeCapabilities(state: LightUiState): DeviceCapabilities {
  const link = state.link
  if (link === null || !link.connected) return NO_CAPABILITIES

  const device = state.devices.find((candidate) => candidate.id === link.deviceId)
  return device?.capabilities ?? NO_CAPABILITIES
}
