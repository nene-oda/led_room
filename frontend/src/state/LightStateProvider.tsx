import { useCallback, useEffect, useMemo, useReducer, type ReactNode } from 'react'

import { apiClient } from '../api/client'
import { brightnessCommand, colorCommand, type ServerEvent } from '../api/dto'
import type { RGBColor } from '../domain/color'
import type { Device } from '../domain/devices'
import type { LightState } from '../domain/light'
import { useLiveField } from '../hooks/useLiveField'
import { useWebSocket } from '../hooks/useWebSocket'
import { describeFailure } from './failures'
import {
  LightStateContext,
  type LightContextValue,
  type LightControls,
  type LightView,
  type RegisteredDevice,
} from './lightStateContext'
import {
  activeCapabilities,
  activeDevice,
  initialLightUiState,
  lightStateReducer,
  visibleLight,
  type LightField,
} from './lightStateReducer'

/**
 * Unico titular del estado compartido de la aplicacion.
 *
 * Reparte el trabajo asi:
 *
 *   - **hidratacion** por REST (`GET /state` + `GET /devices` + `GET /system`),
 *     porque un cliente recien abierto necesita saber en que estado esta la
 *     habitacion y con que adaptador arranco el servidor;
 *   - **actualizaciones** por WebSocket, que es la fuente principal: el
 *     servidor difunde a todos los clientes, incluido el que envio el comando;
 *   - **mutaciones** repartidas entre `/ws` (arrastre) y REST (intenciones), con
 *     optimismo acotado y rollback visible. Color **y brillo** son arrastres:
 *     los dos se limitan en el cliente antes de salir por el socket, y los dos
 *     se cierran con una escritura REST, que es la unica que persiste.
 *
 * Toda la logica de reconciliacion vive en `lightStateReducer`, que es puro y
 * se prueba sin React. Aqui solo quedan los efectos.
 */
export function LightStateProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(lightStateReducer, initialLightUiState)

  const handleEvent = useCallback((event: ServerEvent) => {
    dispatch({ type: 'server-event', event })
  }, [])

  const realtime = useWebSocket(handleEvent)
  const { send } = realtime

  /**
   * Vuelve a pedir el estado completo.
   *
   * No hace falta tras una reconexion del socket —el servidor manda
   * `state.snapshot` como primer frame—, pero si tras conectar o desconectar un
   * dispositivo, porque las capacidades vienen de `GET /devices`.
   */
  const refresh = useCallback(async () => {
    try {
      const [globalState, devices, system] = await Promise.all([
        apiClient.getState(),
        apiClient.listDevices(),
        // Aparte de las otras dos: un backend anterior a `/system` responde 404
        // y eso no puede tumbar la hidratacion. El fallo se traduce a "no lo
        // se", que es lo unico honesto, y la UI se comporta como antes de que
        // el endpoint existiera. Si el backend entero esta caido, las otras dos
        // rechazan igualmente y el aviso sale por el camino de siempre.
        apiClient.getSystemInfo().catch(() => null),
      ])
      dispatch({ type: 'hydrated', state: globalState, devices, system })
    } catch (error) {
      const failure = describeFailure(error)
      dispatch({
        type: 'hydration-failed',
        message: failure.message,
        backendReachable: failure.backendReachable,
      })
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Mientras el socket no este abierto, la numeracion de versiones del servidor
  // deja de ser comparable: puede haberse reiniciado y volver a contar desde
  // cero. Olvidarla aqui es lo que permite aceptar el primer `state.snapshot`
  // de la sesion siguiente sin descartarlo por "viejo".
  useEffect(() => {
    if (realtime.status !== 'open') dispatch({ type: 'session-reset' })
  }, [realtime.status])

  // Hueco de versiones: se perdieron eventos, asi que el estado que tenemos ya
  // no es de fiar y se vuelve a pedir entero. Es el unico camino de vuelta:
  // los eventos perdidos no se retransmiten.
  useEffect(() => {
    if (state.resyncRequested) void refresh()
  }, [refresh, state.resyncRequested])

  /** Una mutacion REST: su respuesta ES el nuevo estado autoritativo. */
  const commit = useCallback(async (field: LightField, run: () => Promise<LightState>) => {
    try {
      dispatch({ type: 'commit-succeeded', field, light: await run() })
    } catch (error) {
      const failure = describeFailure(error)
      dispatch({
        type: 'commit-failed',
        field,
        message: failure.message,
        backendReachable: failure.backendReachable,
      })
    }
  }, [])

  const sendColor = useCallback(
    (color: RGBColor) => {
      send(colorCommand(color))
    },
    [send],
  )

  const persistColor = useCallback(
    (color: RGBColor) => {
      void commit('color', () => apiClient.setColor(color))
    },
    [commit],
  )

  const sendBrightness = useCallback(
    (value: number) => {
      send(brightnessCommand(value))
    },
    [send],
  )

  const persistBrightness = useCallback(
    (value: number) => {
      void commit('brightness', () => apiClient.setBrightness(value))
    },
    [commit],
  )

  const colorField = useLiveField<RGBColor>({ send: sendColor, persist: persistColor })
  const brightnessField = useLiveField<number>({ send: sendBrightness, persist: persistBrightness })

  const device = activeDevice(state)

  /**
   * Conectar o desconectar, con el id explicito.
   *
   * Se rehidrata **pase lo que pase**: en el camino feliz porque las
   * capacidades vienen de `GET /devices`, y en el fallido porque el servidor
   * pudo cambiar igualmente (un alta reciente que no llego a enlazarse por un
   * 409 sigue estando dada de alta) y quedarnos con la lista vieja escondería
   * ese dispositivo. El aviso del fallo sobrevive: rehidratar no lo borra.
   */
  const runLink = useCallback(
    async (deviceId: string, run: (deviceId: string) => Promise<Device>) => {
      dispatch({ type: 'link-started' })
      try {
        await run(deviceId)
      } catch (error) {
        const failure = describeFailure(error, 'link')
        dispatch({
          type: 'link-failed',
          message: failure.message,
          backendReachable: failure.backendReachable,
        })
      }
      await refresh()
    },
    [refresh],
  )

  const controls = useMemo<LightControls>(
    () => ({
      setPower: (on) => {
        dispatch({ type: 'local-change', field: 'power', value: on })
        void commit('power', () => apiClient.setPower(on))
      },
      previewColor: (color) => {
        dispatch({ type: 'local-change', field: 'color', value: color })
        colorField.update(color)
      },
      commitColor: (color) => {
        dispatch({ type: 'local-change', field: 'color', value: color })
        colorField.commit(color)
      },
      setBrightness: (value) => {
        dispatch({ type: 'local-change', field: 'brightness', value })
        brightnessField.update(value)
      },
      connectDevice: (deviceId) => {
        void runLink(deviceId, (id) => apiClient.connectDevice(id))
      },
      disconnectDevice: (deviceId) => {
        void runLink(deviceId, (id) => apiClient.disconnectDevice(id))
      },
      refreshState: () => {
        void refresh()
      },
      dismissNotice: () => {
        dispatch({ type: 'notice-dismissed' })
      },
    }),
    [brightnessField, colorField, commit, refresh, runLink],
  )

  const view = useMemo<LightView>(() => {
    const link = state.link
    const linked = device !== null && link !== null && link.deviceId === device.id

    // Un solo enlace: `connected` sale de comparar con el, nunca del campo
    // homonimo de `GET /devices`, que no lo actualiza el WebSocket.
    const devices: readonly RegisteredDevice[] = state.devices.map((candidate) => ({
      id: candidate.id,
      name: candidate.name,
      address: candidate.address,
      connected: link !== null && link.deviceId === candidate.id && link.connected,
    }))

    return {
      hydration: state.hydration,
      backend: state.backend,
      realtime: realtime.status,
      system: state.system,
      light: visibleLight(state),
      capabilities: activeCapabilities(state),
      effect: {
        runningId: state.effect?.id ?? null,
        stoppedByCommandId: state.effectStoppedByCommand,
      },
      activeSceneId: state.scene?.id ?? null,
      device:
        device === null
          ? null
          : {
              id: device.id,
              name: device.name,
              address: device.address,
              connected: linked && link.connected,
              rssi: linked ? link.rssi : null,
              lastError: linked ? link.lastError : null,
            },
      devices,
      linkPending: state.linkPending,
      notice: state.notice,
    }
  }, [device, realtime.status, state])

  const value = useMemo<LightContextValue>(() => ({ view, controls }), [controls, view])

  return <LightStateContext.Provider value={value}>{children}</LightStateContext.Provider>
}
