import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useDeviceDiscovery } from './useDeviceDiscovery'
import { MIN_VISIBLE_SCAN_MS, SCAN_TIMEOUT_SECONDS } from '../domain/discovery'
import type { SystemInfo } from '../domain/system'

/** Servidor con radio: puede escanear y declara su propio techo. */
const WITH_RADIO: SystemInfo = {
  adapterType: 'lotus_lantern_ble',
  supportsDiscovery: true,
  scanTimeoutSeconds: 6,
}

/** Servidor sin radio: el caso del adaptador nulo, que contesta `200 []` al vuelo. */
const WITHOUT_RADIO: SystemInfo = {
  adapterType: 'null',
  supportsDiscovery: false,
  scanTimeoutSeconds: 10,
}

/**
 * Doble minimo de `Response`.
 *
 * Se evita el `Response` real para que toda la cadena se resuelva en
 * microtareas: con los temporizadores falsos, un cuerpo que necesite una
 * macrotarea dejaria el test colgado.
 */
function reply(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

const DEVICE_BODY = {
  id: 'b2',
  name: 'ELK-BLEDOM',
  adapter_type: 'lotus_lantern_ble',
  address: 'AA:BB',
  enabled: true,
  auto_connect: false,
  connected: false,
  capabilities: {
    rgb: true,
    brightness: true,
    effects: false,
    addressable: false,
    segments: false,
    white_channel: false,
    music_mode: false,
  },
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useDeviceDiscovery', () => {
  it('tras un 409 bloquea el escaneo y lo vuelve a permitir sin recargar', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(reply(409, { detail: { code: 'device_busy', message: 'busy' } })),
    )

    const { result } = renderHook(() => useDeviceDiscovery({ onRegistered: vi.fn(), system: null }))

    await act(async () => {
      result.current.scan()
    })

    // El servidor rechaza al instante, pero el indicador no parpadea: se
    // mantiene el minimo legible antes de publicar el resultado.
    expect(result.current.state.status).toBe('scanning')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MIN_VISIBLE_SCAN_MS)
    })

    expect(result.current.state.status).toBe('blocked')
    expect(result.current.state.message).toContain('Ya hay un escaneo en curso')

    // El servidor no dice cuando quedara libre: se espera lo que dura un
    // escaneo y se reintenta, en vez de dejar el boton muerto para siempre.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SCAN_TIMEOUT_SECONDS * 1000)
    })

    expect(result.current.state.status).toBe('idle')
    expect(result.current.state.message).toBeNull()
  })

  it('sin radio no pide un escaneo ni finge que lo esta haciendo', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, []))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() =>
      useDeviceDiscovery({ onRegistered: vi.fn(), system: WITHOUT_RADIO }),
    )

    expect(result.current.state.radio).toBe('missing')

    await act(async () => {
      result.current.scan()
    })

    // Ni peticion ni estado "buscando": el minimo de visibilidad existe para no
    // hacer parpadear una espera real, no para simular una que no ocurre.
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.state.status).toBe('idle')
  })

  it('usa el techo de escaneo que declara el servidor, no el de respaldo', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, []))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() =>
      useDeviceDiscovery({ onRegistered: vi.fn(), system: WITH_RADIO }),
    )

    expect(result.current.state.radio).toBe('available')
    expect(result.current.state.timeoutSeconds).toBe(WITH_RADIO.scanTimeoutSeconds)

    await act(async () => {
      result.current.scan()
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/devices/scan?timeout=6', expect.anything())
  })

  it('avisa con el id que asigno el servidor, no con la direccion', async () => {
    const onRegistered = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(201, DEVICE_BODY)))

    const { result } = renderHook(() => useDeviceDiscovery({ onRegistered, system: null }))

    await act(async () => {
      result.current.adopt({ name: 'ELK-BLEDOM', address: 'AA:BB', rssi: -50 })
    })

    expect(onRegistered).toHaveBeenCalledWith('b2')
    expect(result.current.state.pendingAddress).toBeNull()
  })

  it('un alta fallida no deja la fila trabajando para siempre', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const { result } = renderHook(() => useDeviceDiscovery({ onRegistered: vi.fn(), system: null }))

    await act(async () => {
      result.current.adopt({ name: null, address: 'AA:BB', rssi: null })
    })

    expect(result.current.state.pendingAddress).toBeNull()
    expect(result.current.state.message).toBe('No se pudo contactar con el servidor.')
  })
})
