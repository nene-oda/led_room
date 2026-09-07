import { describe, expect, it } from 'vitest'

import {
  activeCapabilities,
  initialLightUiState,
  lightStateReducer,
  visibleLight,
  type LightAction,
  type LightUiState,
} from './lightStateReducer'
import { rgb } from '../domain/color'
import type { Device } from '../domain/devices'
import type { GlobalState } from '../domain/state'
import type { ServerEvent } from '../api/dto'

const DEVICE: Device = {
  id: 'a1',
  name: 'Tira del salón',
  adapterType: 'null',
  address: null,
  enabled: true,
  autoConnect: true,
  connected: true,
  capabilities: {
    rgb: true,
    brightness: true,
    effects: true,
    addressable: false,
    segments: false,
    whiteChannel: false,
    musicMode: false,
  },
}

const SERVER_STATE: GlobalState = {
  version: 5,
  device: { deviceId: 'a1', connected: true, rssi: -50, lastError: null },
  light: { power: true, color: rgb(255, 0, 0), brightness: 40 },
  effect: null,
  scene: null,
}

function reduce(state: LightUiState, ...actions: readonly LightAction[]): LightUiState {
  return actions.reduce(lightStateReducer, state)
}

function event(body: ServerEvent): LightAction {
  return { type: 'server-event', event: body }
}

const hydrated = reduce(initialLightUiState, {
  type: 'hydrated',
  state: SERVER_STATE,
  devices: [DEVICE],
})

describe('hidratacion', () => {
  it('toma el estado del servidor como autoritativo', () => {
    expect(hydrated.hydration).toBe('ready')
    expect(hydrated.backend).toBe('reachable')
    expect(visibleLight(hydrated)).toEqual(SERVER_STATE.light)
  })

  it('un fallo al refrescar no borra lo que ya se mostraba, pero avisa', () => {
    const failed = reduce(hydrated, {
      type: 'hydration-failed',
      message: 'No se pudo contactar con el servidor.',
      backendReachable: false,
    })

    expect(failed.hydration).toBe('ready')
    expect(failed.backend).toBe('unreachable')
    expect(failed.notice?.message).toBe('No se pudo contactar con el servidor.')
    expect(visibleLight(failed)).toEqual(SERVER_STATE.light)
  })
})

describe('reconciliacion', () => {
  it('el evento del servidor gana sobre el valor optimista fuera del gesto', () => {
    const state = reduce(
      hydrated,
      { type: 'local-change', field: 'brightness', value: 90 },
      { type: 'commit-succeeded', field: 'brightness', light: { ...SERVER_STATE.light, brightness: 90 } },
      event({ kind: 'brightness', brightness: 20, version: 6 }),
    )

    expect(visibleLight(state).brightness).toBe(20)
  })

  it('durante un gesto, el eco del servidor no pisa el valor local de ese campo', () => {
    const state = reduce(
      hydrated,
      { type: 'local-change', field: 'brightness', value: 90 },
      // Eco de un fotograma anterior del propio arrastre: el servidor difunde a
      // todos los clientes, incluido el emisor.
      event({ kind: 'brightness', brightness: 55, version: 6 }),
    )

    expect(visibleLight(state).brightness).toBe(90)
    // Pero el estado autoritativo si se actualiza: es lo que se ve si el gesto
    // acaba fallando.
    expect(state.server.brightness).toBe(55)
  })

  it('el eco de OTRO campo si retira su valor optimista', () => {
    const state = reduce(
      hydrated,
      { type: 'local-change', field: 'brightness', value: 90 },
      event({ kind: 'color', color: rgb(0, 0, 255), version: 6 }),
    )

    expect(visibleLight(state).color).toEqual(rgb(0, 0, 255))
    expect(visibleLight(state).brightness).toBe(90)
  })

  it('un fallo de la mutacion revierte al valor del servidor y deja aviso', () => {
    const state = reduce(
      hydrated,
      { type: 'local-change', field: 'power', value: false },
      {
        type: 'commit-failed',
        field: 'power',
        message: 'No se pudo escribir en el dispositivo.',
        backendReachable: true,
      },
    )

    expect(visibleLight(state).power).toBe(true)
    expect(state.notice?.message).toBe('No se pudo escribir en el dispositivo.')
    expect(state.backend).toBe('reachable')
  })

  it('un frame de error se muestra sin tocar el estado de la luz', () => {
    const state = reduce(hydrated, event({ kind: 'error', code: 'device_not_connected', message: 'x', version: 6 }))

    expect(state.notice?.message).toBe('No hay ningún dispositivo conectado.')
    expect(visibleLight(state)).toEqual(SERVER_STATE.light)
  })
})

describe('orden de los frames', () => {
  it('descarta un frame con version anterior a la aplicada', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'brightness', brightness: 80, version: 6 }),
      // Snapshot rancio: llega tarde y describe un mundo anterior.
      event({
        kind: 'snapshot',
        version: 5,
        state: { ...SERVER_STATE, light: { ...SERVER_STATE.light, brightness: 40 } },
      }),
    )

    expect(visibleLight(state).brightness).toBe(80)
    expect(state.version).toBe(6)
  })

  it('descarta tambien un frame con la MISMA version ya aplicada', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'brightness', brightness: 80, version: 6 }),
      event({ kind: 'brightness', brightness: 10, version: 6 }),
    )

    expect(visibleLight(state).brightness).toBe(80)
  })

  it('un salto de version aplica el frame y pide rehidratar', () => {
    const state = reduce(hydrated, event({ kind: 'brightness', brightness: 80, version: 9 }))

    expect(visibleLight(state).brightness).toBe(80)
    expect(state.resyncRequested).toBe(true)

    const rehydrated = reduce(state, { type: 'hydrated', state: { ...SERVER_STATE, version: 9 }, devices: [DEVICE] })
    expect(rehydrated.resyncRequested).toBe(false)
  })

  it('tras caerse el socket vuelve a aceptar versiones bajas (el servidor pudo reiniciar)', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'brightness', brightness: 80, version: 9 }),
      { type: 'session-reset' },
      event({ kind: 'snapshot', version: 0, state: { ...SERVER_STATE, version: 0 } }),
    )

    expect(visibleLight(state).brightness).toBe(SERVER_STATE.light.brightness)
    expect(state.version).toBe(0)
  })

  it('una hidratacion REST mas vieja no pisa lo que ya llego por el socket', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'brightness', brightness: 80, version: 9 }),
      { type: 'hydrated', state: { ...SERVER_STATE, version: 7 }, devices: [DEVICE] },
    )

    expect(visibleLight(state).brightness).toBe(80)
    // La lista de dispositivos si se toma: no tiene version que comparar.
    expect(state.devices).toEqual([DEVICE])
  })
})

describe('capacidades', () => {
  it('sin enlace no hay ninguna capacidad', () => {
    const disconnected = reduce(hydrated, event({ kind: 'device', deviceId: 'a1', connected: false, version: 6 }))

    expect(activeCapabilities(disconnected).rgb).toBe(false)
    expect(activeCapabilities(disconnected).brightness).toBe(false)
  })

  it('con enlace, las capacidades salen del dispositivo conectado', () => {
    expect(activeCapabilities(hydrated).rgb).toBe(true)
    expect(activeCapabilities(hydrated).addressable).toBe(false)
  })
})

describe('efecto en curso', () => {
  it('el estado del efecto lo fija el servidor, por evento o por snapshot', () => {
    const started = reduce(hydrated, event({ kind: 'effect', effectId: 'e1', running: true, version: 6 }))
    expect(started.effect).toEqual({ id: 'e1' })

    const rehydrated = reduce(started, {
      type: 'hydrated',
      state: { ...SERVER_STATE, version: 9, effect: { id: 'e2' } },
      devices: [DEVICE],
    })
    expect(rehydrated.effect).toEqual({ id: 'e2' })
  })

  it('descarta la parada de un efecto al que ya sustituyo otro', () => {
    // Misma regla que aplica el servidor: una notificacion tardia no puede
    // apagar el indicador del efecto que el usuario acaba de arrancar.
    const state = reduce(
      hydrated,
      event({ kind: 'effect', effectId: 'e1', running: true, version: 6 }),
      event({ kind: 'effect', effectId: 'e2', running: true, version: 7 }),
      event({ kind: 'effect', effectId: 'e1', running: false, version: 8 }),
    )

    expect(state.effect).toEqual({ id: 'e2' })
  })

  it('un frame de efecto rancio se descarta como cualquier otro', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'effect', effectId: 'e1', running: true, version: 9 }),
      event({ kind: 'effect', effectId: 'e1', running: false, version: 6 }),
    )

    expect(state.effect).toEqual({ id: 'e1' })
  })

  it('atribuye la parada al comando manual que la provoco', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'effect', effectId: 'e1', running: true, version: 6 }),
      { type: 'local-change', field: 'color', value: rgb(0, 0, 255) },
      event({ kind: 'effect', effectId: 'e1', running: false, version: 7 }),
    )

    expect(state.effect).toBeNull()
    expect(state.effectStoppedByCommand).toBe('e1')
  })

  it('un efecto que termina solo no se atribuye al usuario', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'effect', effectId: 'e1', running: true, version: 6 }),
      event({ kind: 'effect', effectId: 'e1', running: false, version: 7 }),
    )

    expect(state.effectStoppedByCommand).toBeNull()
  })

  it('arrancar otro efecto cierra el episodio anterior', () => {
    const state = reduce(
      hydrated,
      event({ kind: 'effect', effectId: 'e1', running: true, version: 6 }),
      { type: 'local-change', field: 'power', value: false },
      event({ kind: 'effect', effectId: 'e1', running: false, version: 7 }),
      event({ kind: 'effect', effectId: 'e2', running: true, version: 8 }),
    )

    expect(state.effect).toEqual({ id: 'e2' })
    expect(state.effectStoppedByCommand).toBeNull()
  })
})

describe('escena activa', () => {
  it('la fija el servidor, por evento o por snapshot', () => {
    const activated = reduce(hydrated, event({ kind: 'scene', sceneId: 's1', version: 6 }))

    expect(activated.scene).toEqual({ id: 's1' })

    const snapshot = reduce(
      activated,
      event({
        kind: 'snapshot',
        state: { ...SERVER_STATE, version: 7, scene: null },
        version: 7,
      }),
    )

    // El snapshot manda tambien para vaciarla: quien decide cuando una escena
    // deja de estar puesta es el servidor.
    expect(snapshot.scene).toBeNull()
  })

  it('un frame de escena rancio se descarta como cualquier otro', () => {
    const activated = reduce(hydrated, event({ kind: 'scene', sceneId: 's1', version: 6 }))
    const stale = reduce(activated, event({ kind: 'scene', sceneId: 's0', version: 5 }))

    expect(stale.scene).toEqual({ id: 's1' })
  })

  it('un comando manual NO la vacia: esa ranura solo la escribe el servidor', () => {
    // El servidor detiene el efecto de la escena al recibir un comando manual,
    // pero que la escena siga puesta o no lo decide el, y hay escenas de color
    // fijo cuyo efecto termina solo. Deducirlo aqui mentiria en los dos casos.
    const activated = reduce(
      hydrated,
      event({ kind: 'scene', sceneId: 's1', version: 6 }),
      { type: 'local-change', field: 'brightness', value: 10 },
      event({ kind: 'effect', effectId: 'e1', running: false, version: 7 }),
    )

    expect(activated.scene).toEqual({ id: 's1' })
  })
})
