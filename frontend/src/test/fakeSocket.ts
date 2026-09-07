/**
 * Doble de un WebSocket para los tests.
 *
 * Implementa el puerto `SocketLike` del cliente de tiempo real, asi que sirve
 * tanto inyectado (`createSocket`) como sustituyendo al global `WebSocket`, y
 * permite provocar apertura, cierre y frames entrantes sin red ni jsdom.
 */
export class FakeSocket {
  static created: FakeSocket[] = []

  static reset(): void {
    FakeSocket.created = []
  }

  static get last(): FakeSocket {
    const socket = FakeSocket.created.at(-1)
    if (socket === undefined) throw new Error('No se creó ningún socket')
    return socket
  }

  readonly sent: string[] = []
  closed = false

  onopen: ((event: unknown) => void) | null = null
  onclose: ((event: unknown) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null

  constructor(readonly url: string) {
    FakeSocket.created.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.closed = true
    this.onclose?.({})
  }

  /** Simula que el servidor acepto la conexion. */
  open(): void {
    this.onopen?.({})
  }

  /** Simula una caida del enlace (no un cierre pedido por el cliente). */
  drop(): void {
    this.onclose?.({})
  }

  /** Simula un frame servidor -> cliente. */
  emit(frame: { type: string; version?: number; payload?: unknown }): void {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
}
