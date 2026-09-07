/**
 * Cliente de tiempo real. **Sin React**: solo ciclo de vida del socket.
 *
 * Responsabilidades, y ninguna mas:
 *   - derivar la URL del origen actual (`ws://` o `wss://`),
 *   - abrir, cerrar y reabrir la conexion con backoff exponencial y jitter,
 *   - publicar el estado del enlace y los eventos ya traducidos a dominio.
 *
 * La decodificacion vive en `dto.ts` y la reconciliacion en `state/`. Aqui no
 * hay ninguna regla de producto: este modulo no sabe que es el brillo.
 *
 * **Por que la primera conexion tambien se programa con un temporizador**: en
 * `StrictMode` React monta, desmonta y vuelve a montar. Si `connect()` abriera
 * el socket de forma sincrona, ese ciclo abriria un socket para cerrarlo en el
 * acto en cada arranque en desarrollo. Programarla (aunque sea a 0 ms) hace que
 * un `close()` del mismo tick la cancele antes de que exista, y reutiliza el
 * mismo camino que la reconexion en vez de duplicarlo.
 */
import { parseServerEvent, type ClientCommand, type ServerEvent } from './dto'
import type { RealtimeStatus } from '../domain/connection'

/**
 * Lo minimo que este cliente necesita de un socket.
 *
 * Es un puerto, no la interfaz `WebSocket` del navegador: los tests inyectan un
 * doble sin fabricar `MessageEvent`, y el dia que el transporte sea otro
 * (EventSource, un canal de prueba) solo cambia el adaptador de abajo.
 */
export interface SocketLike {
  send(data: string): void
  close(): void
  onopen: ((event: unknown) => void) | null
  onclose: ((event: unknown) => void) | null
  onerror: ((event: unknown) => void) | null
  onmessage: ((event: { data: unknown }) => void) | null
}

export interface BackoffOptions {
  /** Primer retardo de reconexion. */
  readonly baseDelayMs?: number
  /** Techo del retardo: sin el, la espera crece hasta dejar de reintentarse. */
  readonly maxDelayMs?: number
  /** Inyectable para hacer el jitter determinista en los tests. */
  readonly random?: () => number
}

export interface RealtimeClientOptions extends BackoffOptions {
  readonly onEvent: (event: ServerEvent) => void
  readonly onStatusChange: (status: RealtimeStatus) => void
  /** Por defecto se deriva de `window.location`. */
  readonly url?: string
  readonly createSocket?: (url: string) => SocketLike
}

export const DEFAULT_BASE_DELAY_MS = 500
export const DEFAULT_MAX_DELAY_MS = 30_000

/**
 * URL del WebSocket derivada del origen.
 *
 * Nunca se escribe a mano: el mismo bundle se sirve hoy en
 * `http://192.168.x.x:8000` y podria servirse en `https://`, donde el navegador
 * bloquearia un `ws://`.
 */
export function realtimeUrl(location: { protocol: string; host: string }): string {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${location.host}/ws`
}

/**
 * Retardo del intento `attempt` (0 = primer reintento).
 *
 * Exponencial con techo y **jitter** en la mitad alta del intervalo: sin jitter,
 * todos los clientes de la casa reconectan en el mismo milisegundo justo cuando
 * el backend acaba de levantarse.
 */
export function backoffDelayMs(attempt: number, options: BackoffOptions = {}): number {
  const {
    baseDelayMs = DEFAULT_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_MAX_DELAY_MS,
    random = Math.random,
  } = options

  const capped = Math.min(maxDelayMs, baseDelayMs * 2 ** Math.max(0, attempt))
  return Math.round(capped / 2 + (capped / 2) * random())
}

/** Adaptador del `WebSocket` del navegador al puerto `SocketLike`. */
function browserSocket(url: string): SocketLike {
  const socket = new WebSocket(url)
  const port: SocketLike = {
    send: (data) => {
      socket.send(data)
    },
    close: () => {
      socket.close()
    },
    onopen: null,
    onclose: null,
    onerror: null,
    onmessage: null,
  }

  socket.onopen = (event) => port.onopen?.(event)
  socket.onclose = (event) => port.onclose?.(event)
  socket.onerror = (event) => port.onerror?.(event)
  socket.onmessage = (event) => port.onmessage?.({ data: event.data })

  return port
}

export class RealtimeClient {
  readonly #options: RealtimeClientOptions
  readonly #url: string
  readonly #createSocket: (url: string) => SocketLike

  #socket: SocketLike | null = null
  #timer: ReturnType<typeof setTimeout> | null = null
  #attempt = 0
  #status: RealtimeStatus = 'closed'
  /** Cerrado por nosotros: no se reintenta y no hay backoff que disparar. */
  #stopped = true

  constructor(options: RealtimeClientOptions) {
    this.#options = options
    this.#url = options.url ?? realtimeUrl(window.location)
    this.#createSocket = options.createSocket ?? browserSocket
  }

  get status(): RealtimeStatus {
    return this.#status
  }

  /** Abre la conexion. Idempotente: llamarla dos veces no abre dos sockets. */
  connect(): void {
    if (!this.#stopped) return
    this.#stopped = false
    this.#attempt = 0
    this.#setStatus('connecting')
    this.#schedule(0)
  }

  /** Cierra y **deja de reintentar**: un cierre nuestro no es una caida. */
  close(): void {
    this.#stopped = true
    this.#clearTimer()
    this.#detach()
    this.#setStatus('closed')
  }

  /**
   * Envia un comando si el enlace esta abierto.
   *
   * Devuelve `false` cuando no lo esta, y **no encola**: los valores de un
   * arrastre caducan en decenas de milisegundos, asi que una cola solo serviria
   * para reproducir colores viejos al reconectar. El estado correcto lo
   * restablece el `state.snapshot` que el servidor manda al reconectar.
   */
  send(command: ClientCommand): boolean {
    if (this.#socket === null || this.#status !== 'open') return false
    this.#socket.send(JSON.stringify(command))
    return true
  }

  #schedule(delayMs: number): void {
    this.#clearTimer()
    this.#timer = setTimeout(() => {
      this.#timer = null
      this.#open()
    }, delayMs)
  }

  #open(): void {
    if (this.#stopped) return

    const socket = this.#createSocket(this.#url)
    this.#socket = socket

    socket.onopen = () => {
      this.#attempt = 0
      this.#setStatus('open')
    }

    socket.onmessage = (event) => {
      if (typeof event.data !== 'string') return
      const parsed = parseServerEvent(event.data)
      if (parsed !== null) this.#options.onEvent(parsed)
    }

    // `onerror` no aporta motivo (el navegador lo oculta por seguridad) y
    // siempre viene seguido de `onclose`: el reintento lo gobierna `onclose`,
    // asi que un fallo de red y una caida limpia siguen el mismo camino.
    socket.onclose = () => {
      this.#socket = null
      if (this.#stopped) return
      this.#setStatus('reconnecting')
      this.#schedule(backoffDelayMs(this.#attempt, this.#options))
      this.#attempt += 1
    }
  }

  #detach(): void {
    const socket = this.#socket
    if (socket === null) return
    this.#socket = null
    socket.onopen = null
    socket.onclose = null
    socket.onerror = null
    socket.onmessage = null
    socket.close()
  }

  #clearTimer(): void {
    if (this.#timer !== null) {
      clearTimeout(this.#timer)
      this.#timer = null
    }
  }

  #setStatus(status: RealtimeStatus): void {
    if (this.#status === status) return
    this.#status = status
    this.#options.onStatusChange(status)
  }
}
