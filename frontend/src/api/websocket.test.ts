import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { colorCommand, type ServerEvent } from './dto'
import {
  backoffDelayMs,
  realtimeUrl,
  RealtimeClient,
  DEFAULT_MAX_DELAY_MS,
  type RealtimeClientOptions,
} from './websocket'
import { rgb } from '../domain/color'
import type { RealtimeStatus } from '../domain/connection'
import { FakeSocket } from '../test/fakeSocket'

beforeEach(() => {
  vi.useFakeTimers()
  FakeSocket.reset()
})

afterEach(() => {
  vi.useRealTimers()
})

interface Harness {
  readonly client: RealtimeClient
  readonly events: ServerEvent[]
  readonly statuses: RealtimeStatus[]
}

function harness(overrides: Partial<RealtimeClientOptions> = {}): Harness {
  const events: ServerEvent[] = []
  const statuses: RealtimeStatus[] = []

  const client = new RealtimeClient({
    url: 'ws://test/ws',
    createSocket: (url) => new FakeSocket(url),
    // Jitter determinista: el maximo del intervalo, para poder afirmar el techo.
    random: () => 1,
    baseDelayMs: 500,
    onEvent: (event) => events.push(event),
    onStatusChange: (status) => statuses.push(status),
    ...overrides,
  })

  return { client, events, statuses }
}

describe('realtimeUrl', () => {
  it('deriva el esquema del origen en vez de horneralo', () => {
    expect(realtimeUrl({ protocol: 'http:', host: '192.168.1.50:8000' })).toBe(
      'ws://192.168.1.50:8000/ws',
    )
    expect(realtimeUrl({ protocol: 'https:', host: 'led.local' })).toBe('wss://led.local/ws')
  })
})

describe('backoffDelayMs', () => {
  it('crece exponencialmente y se detiene en el techo', () => {
    const options = { baseDelayMs: 500, random: () => 1 }

    expect(backoffDelayMs(0, options)).toBe(500)
    expect(backoffDelayMs(1, options)).toBe(1000)
    expect(backoffDelayMs(2, options)).toBe(2000)
    expect(backoffDelayMs(20, options)).toBe(DEFAULT_MAX_DELAY_MS)
  })

  it('el jitter nunca saca el retardo del intervalo acotado', () => {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      for (const random of [() => 0, () => 0.5, () => 1]) {
        const delay = backoffDelayMs(attempt, { baseDelayMs: 500, random })
        expect(delay).toBeGreaterThanOrEqual(250)
        expect(delay).toBeLessThanOrEqual(DEFAULT_MAX_DELAY_MS)
      }
    }
  })
})

describe('RealtimeClient', () => {
  it('abre un solo socket y anuncia connecting y open', () => {
    const { client, statuses } = harness()

    client.connect()
    vi.advanceTimersByTime(0)
    FakeSocket.last.open()

    expect(FakeSocket.created).toHaveLength(1)
    expect(FakeSocket.last.url).toBe('ws://test/ws')
    expect(statuses).toEqual(['connecting', 'open'])
  })

  it('no abre dos sockets si se monta, se desmonta y se vuelve a montar (StrictMode)', () => {
    const { client } = harness()

    // El ciclo completo de React 19 en desarrollo, dentro del mismo tick.
    client.connect()
    client.close()
    client.connect()
    vi.advanceTimersByTime(0)

    expect(FakeSocket.created).toHaveLength(1)
  })

  it('envia comandos solo con el enlace abierto', () => {
    const { client } = harness()
    client.connect()
    vi.advanceTimersByTime(0)

    expect(client.send(colorCommand(rgb(1, 2, 3)))).toBe(false)

    FakeSocket.last.open()
    expect(client.send(colorCommand(rgb(1, 2, 3)))).toBe(true)
    expect(FakeSocket.last.sent).toEqual(['{"type":"light.color","payload":{"r":1,"g":2,"b":3}}'])
  })

  it('entrega los frames del servidor ya traducidos a dominio', () => {
    const { client, events } = harness()
    client.connect()
    vi.advanceTimersByTime(0)
    FakeSocket.last.open()

    FakeSocket.last.emit({ type: 'light.color.changed', version: 3, payload: { color: '#00FF00' } })

    expect(events).toEqual([{ kind: 'color', color: rgb(0, 255, 0), version: 3 }])
  })

  it('reconecta con retardos crecientes y acotados tras cada caida', () => {
    const { client, statuses } = harness()
    client.connect()
    vi.advanceTimersByTime(0)
    FakeSocket.last.open()

    // Primera caida: 500 ms.
    FakeSocket.last.drop()
    expect(statuses.at(-1)).toBe('reconnecting')
    vi.advanceTimersByTime(499)
    expect(FakeSocket.created).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.created).toHaveLength(2)

    // Segunda caida sin haber llegado a abrir: 1000 ms.
    FakeSocket.last.drop()
    vi.advanceTimersByTime(999)
    expect(FakeSocket.created).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.created).toHaveLength(3)
  })

  it('reinicia el backoff cuando la conexion vuelve a abrirse', () => {
    const { client } = harness()
    client.connect()
    vi.advanceTimersByTime(0)
    FakeSocket.last.open()

    FakeSocket.last.drop()
    vi.advanceTimersByTime(500)
    FakeSocket.last.open()

    FakeSocket.last.drop()
    vi.advanceTimersByTime(500)
    expect(FakeSocket.created).toHaveLength(3)
  })

  it('un cierre pedido por el cliente no dispara reconexion', () => {
    const { client, statuses } = harness()
    client.connect()
    vi.advanceTimersByTime(0)
    FakeSocket.last.open()

    client.close()
    vi.advanceTimersByTime(DEFAULT_MAX_DELAY_MS)

    expect(FakeSocket.created).toHaveLength(1)
    expect(statuses.at(-1)).toBe('closed')
  })
})
