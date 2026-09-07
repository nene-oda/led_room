/**
 * Backend simulado en la frontera real: `fetch` para REST y un doble de
 * `WebSocket` para el tiempo real.
 *
 * Vive aparte porque lo comparten los recorridos de control y los de alta de
 * dispositivos. Sin esto, el segundo fichero de tests copiaria las rutas y los
 * fixtures, y al cambiar un contrato solo se actualizaria uno de los dos.
 */
import { act, waitFor } from '@testing-library/react'
import { expect, vi } from 'vitest'

import { FakeSocket } from './fakeSocket'

export const CAPABILITIES = {
  rgb: true,
  brightness: true,
  effects: true,
  addressable: false,
  segments: false,
  white_channel: false,
  music_mode: false,
}

export const DEVICE = {
  id: 'a1',
  name: 'Tira del salón',
  adapter_type: 'null',
  address: 'AA:BB:CC',
  enabled: true,
  auto_connect: true,
  connected: true,
  capabilities: CAPABILITIES,
}

/** Un efecto guardado, con la forma exacta de `EffectRead`. */
export const EFFECT = {
  id: 'e1',
  name: 'Atardecer',
  type: 'SMOOTH_CYCLE',
  description: null,
  loop: true,
  speed: 50,
  fps: 20,
  transition_ms: 2000,
  min_brightness: 0,
  max_brightness: 100,
  is_builtin: false,
  steps: [
    { position: 0, color: '#FF6A00', brightness: null, duration_ms: null, easing: null },
    { position: 1, color: '#7B00FF', brightness: null, duration_ms: null, easing: null },
  ],
}

/** Una escena guardada, con la forma exacta de `SceneRead`. */
export const SCENE = {
  id: 's1',
  name: 'Noche',
  description: null,
  icon: null,
  is_builtin: false,
  // Favorita: es lo que la pone en la barra de escenas rapidas, que es donde se
  // activa a diario.
  is_favorite: true,
  targets: [
    { device_id: 'a1', effect_id: 'e1', brightness: null, speed: null, enabled: true },
  ],
}

/** Un perfil guardado, con la forma exacta de `ProfileRead`. */
export const PROFILE = {
  id: 'p1',
  name: 'Cine',
  description: null,
  icon: null,
  is_builtin: false,
  scenes: [{ scene_id: 's1', position: 0, is_default: true }],
  // Ya resuelto por el servidor: el cliente no reimplementa el desempate.
  default_scene_id: 's1',
}

/**
 * Respuesta de `GET /system` de un servidor CON radio.
 *
 * No entra en las rutas por defecto a proposito: asi el stub base sigue
 * representando a un backend que todavia no publica el endpoint, que es el
 * escenario en el que la UI no puede afirmar nada. Los tests que quieran hablar
 * de la radio lo declaran explicitamente.
 */
export const SYSTEM = {
  adapter_type: 'lotus_lantern_ble',
  supports_discovery: true,
  scan_timeout_seconds: 10,
}

/** El caso del usuario: adaptador nulo, sin radio, `200 []` instantaneo. */
export const SYSTEM_WITHOUT_RADIO = {
  adapter_type: 'null',
  supports_discovery: false,
  scan_timeout_seconds: 10,
}

export const STATE = {
  version: 3,
  device: { device_id: 'a1', connected: true, rssi: -50, last_error: null },
  light: { power: false, color: '#FF0000', brightness: 40 },
  effect: null,
  scene: null,
}

/** Una ruta puede tardar: asi se puede observar el estado "en curso". */
export type Route = () => Response | Promise<Response>

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function stubBackend(overrides: Record<string, Route> = {}): ReturnType<typeof vi.fn> {
  const routes: Record<string, Route> = {
    'GET /api/v1/state': () => json(STATE),
    'GET /api/v1/devices': () => json([DEVICE]),
    'GET /api/v1/effects': () => json([EFFECT]),
    'GET /api/v1/scenes': () => json([SCENE]),
    'GET /api/v1/profiles': () => json([PROFILE]),
    ...overrides,
  }

  const fetchMock = vi.fn((input: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? 'GET'} ${input}`]
    return Promise.resolve(route === undefined ? json({ detail: 'Not Found' }, 404) : route())
  })

  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('WebSocket', FakeSocket)
  return fetchMock
}

/** Espera a que se cree el socket y simula que el servidor lo acepta. */
export async function openSocket(): Promise<void> {
  await waitFor(() => {
    expect(FakeSocket.created).toHaveLength(1)
  })
  act(() => {
    FakeSocket.last.open()
  })
}
