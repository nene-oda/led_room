/**
 * Estado global del servidor tal y como lo ve el cliente.
 *
 * Misma forma que `GET /api/v1/state` y que el frame `state.snapshot`
 * (backend/app/api/schemas/state.py). El backend es la autoridad: esto es una
 * replica, nunca una segunda fuente de verdad.
 *
 * `scene` es la escena que el servidor da por activa. **Es una ranura del
 * servidor, no una deduccion del cliente**: se rellena con el snapshot y con
 * `scene.activated`, y solo el servidor la vacia. Derivarla del efecto en curso
 * seria mentir en los dos sentidos -- una escena de color fijo (`STATIC`) deja
 * de tener efecto sonando en cuanto termina, y un efecto suelto arrancado desde
 * la biblioteca no convierte a nadie en escena activa.
 */
import type { DeviceLink } from './devices'
import type { LightState } from './light'

/**
 * El efecto que suena ahora mismo.
 *
 * El servidor publica `{running, id}`, pero aqui solo se guarda el id: en el
 * contrato `running` es siempre `true` cuando el campo existe y `null` cuando
 * no hay nada sonando, asi que un `{running: false, id}` en el cliente seria un
 * estado imposible que alguien acabaria pintando.
 */
export interface RunningEffect {
  readonly id: string
}

/**
 * La escena que el servidor da por activa.
 *
 * Solo el id, por el mismo motivo que `RunningEffect`: el catalogo (nombres,
 * objetivos) llega por `GET /scenes` y no viaja por el WebSocket, asi que
 * copiarlo aqui crearia una segunda copia que nadie mantendria al dia.
 */
export interface ActiveScene {
  readonly id: string
}

export interface GlobalState {
  /**
   * Estrictamente creciente dentro de una ejecucion del servidor. Sirve para
   * detectar que nos perdimos eventos; no para ordenar entre reinicios, donde
   * vuelve a empezar.
   */
  readonly version: number
  readonly device: DeviceLink | null
  readonly light: LightState
  /** `null` = no hay ningun efecto en marcha. */
  readonly effect: RunningEffect | null
  /** `null` = el servidor no da ninguna escena por activa. */
  readonly scene: ActiveScene | null
}
