import { useCallback, useEffect, useRef, useState } from 'react'

import { RealtimeClient } from '../api/websocket'
import type { ClientCommand, ServerEvent } from '../api/dto'
import type { RealtimeStatus } from '../domain/connection'

export interface RealtimeChannel {
  readonly status: RealtimeStatus
  /** `false` si el enlace no esta abierto y el comando se descarto. */
  readonly send: (command: ClientCommand) => boolean
}

/**
 * **La unica conexion WebSocket de la aplicacion.**
 *
 * Lo usa el proveedor de estado y nadie mas: si cada componente abriera la
 * suya, el servidor difundiria N veces el mismo evento y cada rearranque del
 * backend produciria N reconexiones simultaneas.
 *
 * `onEvent` puede cambiar en cada render sin reabrir nada: se guarda en una ref
 * y el efecto no depende de el. Si dependiera, cualquier render del proveedor
 * cerraria y abriria el socket.
 *
 * En `StrictMode` el efecto se monta, se desmonta y se vuelve a montar. El
 * cliente programa su primera conexion en un temporizador, asi que el
 * `close()` de la limpieza la cancela antes de abrir nada: un solo socket y
 * ningun reintento con backoff (el contador vive en la instancia, que se
 * descarta).
 */
export function useWebSocket(onEvent: (event: ServerEvent) => void): RealtimeChannel {
  const [status, setStatus] = useState<RealtimeStatus>('connecting')
  const onEventRef = useRef(onEvent)
  const clientRef = useRef<RealtimeClient | null>(null)

  useEffect(() => {
    onEventRef.current = onEvent
  })

  useEffect(() => {
    const client = new RealtimeClient({
      onEvent: (event) => {
        onEventRef.current(event)
      },
      onStatusChange: setStatus,
    })

    clientRef.current = client
    client.connect()

    return () => {
      clientRef.current = null
      client.close()
    }
  }, [])

  const send = useCallback((command: ClientCommand): boolean => {
    return clientRef.current?.send(command) ?? false
  }, [])

  return { status, send }
}
