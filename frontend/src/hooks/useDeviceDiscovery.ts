import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, apiClient } from '../api/client'
import type { DiscoveredDevice } from '../domain/devices'
import {
  MIN_VISIBLE_SCAN_MS,
  radioStatus,
  scanTimeoutOf,
  sortByProximity,
  type RadioStatus,
} from '../domain/discovery'
import type { SystemInfo } from '../domain/system'
import { describeFailure } from '../state/failures'

/**
 * Estado del escaneo.
 *
 * `blocked` es distinto de `failed` a proposito: significa que el servidor ya
 * esta escaneando para otro cliente y que reintentar ahora volveria a fallar,
 * asi que el boton se queda deshabilitado un rato. Un `failed` normal si se
 * puede reintentar de inmediato.
 */
export type ScanStatus = 'idle' | 'scanning' | 'done' | 'blocked' | 'failed'

/**
 * Lo que cambia con cada escaneo.
 *
 * Es lo unico que este hook **guarda**. Lo que sabe el servidor de si mismo se
 * deriva de `system`, que entra por parametro.
 */
interface ScanState {
  readonly status: ScanStatus
  /** Ultimo escaneo, ya ordenado de mas cerca a mas lejos. */
  readonly results: readonly DiscoveredDevice[]
  /** Explicacion del ultimo fallo. Los textos de exito los pone la vista. */
  readonly message: string | null
  /** Direccion que se esta dando de alta ahora mismo, o `null`. */
  readonly pendingAddress: string | null
}

export interface DiscoveryView extends ScanState {
  /**
   * Si el servidor puede buscar por radio, segun el propio servidor.
   *
   * **Derivado, no copiado**: sale de `system`, cuyo unico titular es el estado
   * compartido. Viaja en este modelo de vista para que el panel no necesite un
   * segundo canal para una sola pregunta.
   */
  readonly radio: RadioStatus
  /** Cota superior de un escaneo, en segundos. Es lo que se anuncia y se dibuja. */
  readonly timeoutSeconds: number
  /**
   * Nombre del adaptador con el que arranco el servidor, o `null`.
   *
   * **No decide nada**: solo se nombra al explicar por que no se puede buscar,
   * para que quien administre el servidor sepa exactamente que esta cambiando.
   */
  readonly adapterType: string | null
}

export interface DeviceDiscovery {
  readonly state: DiscoveryView
  readonly scan: () => void
  /** Da de alta un resultado del escaneo y avisa con el id que asigno el servidor. */
  readonly adopt: (candidate: DiscoveredDevice) => void
}

const INITIAL: ScanState = {
  status: 'idle',
  results: [],
  message: null,
  pendingAddress: null,
}

/**
 * Descubrimiento y alta de dispositivos.
 *
 * Vive fuera del estado global a proposito: es **estado de una tarea**, no
 * estado compartido del servidor. Solo lo mira el panel de descubrimiento, se
 * tira en cuanto se cierra la sesion de trabajo y nadie mas necesita
 * enterarse. Meterlo en el proveedor obligaria a re-renderizar la pantalla de
 * control entera cada vez que llega un resultado de escaneo.
 *
 * Lo que si es estado compartido —la lista de dispositivos dados de alta, el
 * enlace y las capacidades del servidor— sigue siendo del proveedor: por eso el
 * alta no lo guarda aqui, sino que lo notifica con `onRegistered` para que el
 * titular vuelva a leerlo del servidor, y por eso `system` **entra** en vez de
 * pedirse otra vez.
 *
 * @param onRegistered Se invoca con el id que asigno el servidor tras un alta
 *   correcta. Dependencia explicita: el hook no conoce el estado global.
 * @param system Lo que el servidor dijo de si mismo, o `null` si aun no lo ha
 *   dicho. Decide si se puede escanear y cuanto puede tardar.
 */
export function useDeviceDiscovery({
  onRegistered,
  system,
}: {
  readonly onRegistered: (deviceId: string) => void
  readonly system: SystemInfo | null
}): DeviceDiscovery {
  const [state, setState] = useState<ScanState>(INITIAL)
  const unblockRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const radio = radioStatus(system)
  const timeoutSeconds = scanTimeoutOf(system)

  useEffect(
    () => () => {
      if (unblockRef.current !== null) clearTimeout(unblockRef.current)
    },
    [],
  )

  /**
   * Espera lo que dura un escaneo antes de volver a permitirlo.
   *
   * El servidor no dice cuando quedara libre, asi que se usa la unica cota
   * conocida: lo que dura un escaneo. Se desbloquea solo; dejar el boton
   * muerto hasta recargar la pagina seria peor que reintentar de mas.
   */
  const blockScanning = useCallback(() => {
    if (unblockRef.current !== null) clearTimeout(unblockRef.current)
    unblockRef.current = setTimeout(() => {
      unblockRef.current = null
      setState((current) =>
        current.status === 'blocked' ? { ...current, status: 'idle', message: null } : current,
      )
    }, timeoutSeconds * 1000)
  }, [timeoutSeconds])

  const scan = useCallback(() => {
    // Sin radio no hay nada que buscar. El boton ya esta deshabilitado con su
    // explicacion; esto cierra el camino tambien por codigo, para que no exista
    // ninguna forma de fingir una busqueda que el servidor no puede hacer.
    if (radio === 'missing') return

    setState((current) => ({ ...current, status: 'scanning', message: null }))
    const startedAt = Date.now()

    void (async () => {
      try {
        const found = await apiClient.scanDevices(timeoutSeconds)
        await stayVisible(startedAt)
        setState((current) => ({
          ...current,
          status: 'done',
          results: sortByProximity(found),
          message: null,
        }))
      } catch (error) {
        // 409 `device_busy` aqui significa "hay otro escaneo en curso", no
        // "hay otro dispositivo enlazado": de ahi el contexto.
        const busy = error instanceof ApiError && error.code === 'device_busy'
        const message = describeFailure(error, 'scan').message
        await stayVisible(startedAt)
        setState((current) => ({
          ...current,
          status: busy ? 'blocked' : 'failed',
          message,
        }))
        if (busy) blockScanning()
      }
    })()
  }, [blockScanning, radio, timeoutSeconds])

  const adopt = useCallback(
    (candidate: DiscoveredDevice) => {
      setState((current) => ({ ...current, pendingAddress: candidate.address, message: null }))

      void (async () => {
        try {
          const device = await apiClient.registerDevice({
            name: candidate.name,
            address: candidate.address,
          })
          setState((current) => ({ ...current, pendingAddress: null }))
          onRegistered(device.id)
        } catch (error) {
          setState((current) => ({
            ...current,
            pendingAddress: null,
            message: describeFailure(error).message,
          }))
        }
      })()
    },
    [onRegistered],
  )

  const adapterType = system?.adapterType ?? null

  const view = useMemo<DiscoveryView>(
    () => ({ ...state, radio, timeoutSeconds, adapterType }),
    [adapterType, radio, state, timeoutSeconds],
  )

  return { state: view, scan, adopt }
}

/**
 * Retiene el resultado hasta que el escaneo lleve visible lo minimo legible.
 *
 * Sin esto, un servidor que contesta al instante —el adaptador nulo lo hace en
 * milisegundos— hace aparecer y desaparecer el progreso en el mismo fotograma:
 * lo que el usuario percibe es que el panel se ha recargado solo, no que se ha
 * buscado. **No alarga una espera que no existio**: cuando el servidor no tiene
 * radio no se llega a escanear, asi que esta funcion no se ejecuta.
 */
function stayVisible(startedAt: number): Promise<void> {
  const remaining = MIN_VISIBLE_SCAN_MS - (Date.now() - startedAt)
  if (remaining <= 0) return Promise.resolve()
  return new Promise((resolve) => setTimeout(resolve, remaining))
}
