import { useCallback, useEffect, useRef } from 'react'

import { useThrottledValue } from './useThrottledValue'

/**
 * Un campo que se manipula con un gesto continuo (color, brillo).
 *
 * Encapsula el **reparto REST / WebSocket**, que no es una preferencia de
 * estilo sino una regla del servidor:
 *
 *   - `update` es un fotograma del gesto. Va por `/ws`, limitado en el cliente
 *     y otra vez en el servidor. **El WebSocket no persiste nada.**
 *   - `commit` es el cierre del gesto o una intencion discreta (un preset). Va
 *     por REST, que es lo unico que el backend guarda, y ademas cancela en el
 *     servidor el arrastre pendiente.
 *
 * Un gesto puede terminar sin que nadie avise —un `<input type="range">` no
 * distingue "he soltado" de "sigo arrastrando"—, asi que `update` programa
 * ademas un commit de reserva cuando el valor lleva `settleMs` sin cambiar.
 * Sin el, mover el brillo y soltar dejaria el valor aplicado pero **no
 * guardado**, y se perderia al reiniciar. Un `commit` explicito (el
 * `pointerup` del selector de color) lo adelanta y cancela.
 */
export interface LiveFieldOptions<T> {
  /** Envio de baja latencia por WebSocket. */
  readonly send: (value: T) => void
  /** Escritura persistente por REST. El resultado lo gestiona quien la pasa. */
  readonly persist: (value: T) => void
  readonly intervalMs?: number
  readonly settleMs?: number
}

export interface LiveField<T> {
  readonly update: (value: T) => void
  readonly commit: (value: T) => void
}

/**
 * Intervalo minimo entre mensajes de arrastre: ~20 por segundo, el mismo orden
 * que `LED_ROOM_BLE_MAX_UPDATES_PER_SECOND` en el servidor.
 */
export const LIVE_INTERVAL_MS = 50

/**
 * Inactividad que se considera "gesto terminado".
 *
 * Lo bastante largo para no escribir en la base a mitad de un arrastre lento y
 * lo bastante corto para que soltar y apagar el movil conserve el valor.
 */
export const SETTLE_MS = 300

export function useLiveField<T>({
  send,
  persist,
  intervalMs = LIVE_INTERVAL_MS,
  settleMs = SETTLE_MS,
}: LiveFieldOptions<T>): LiveField<T> {
  const pushLive = useThrottledValue(send, intervalMs)

  const persistRef = useRef(persist)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latestRef = useRef<{ value: T } | null>(null)

  useEffect(() => {
    persistRef.current = persist
  })

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => () => clearTimer(), [clearTimer])

  const commit = useCallback(
    (value: T) => {
      clearTimer()
      latestRef.current = null
      persistRef.current(value)
    },
    [clearTimer],
  )

  const update = useCallback(
    (value: T) => {
      latestRef.current = { value }
      pushLive(value)

      clearTimer()
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        const latest = latestRef.current
        latestRef.current = null
        if (latest !== null) persistRef.current(latest.value)
      }, settleMs)
    },
    [clearTimer, pushLive, settleMs],
  )

  return { update, commit }
}
