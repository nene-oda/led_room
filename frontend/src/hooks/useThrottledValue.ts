import { useCallback, useEffect, useRef } from 'react'

/**
 * Limitador de un flujo de valores continuo, **leading + trailing**.
 *
 * Devuelve una funcion a la que se le empujan todos los valores de un gesto
 * (un `pointermove` dispara a 60-120 Hz) y que emite como mucho uno por
 * intervalo, con dos garantias:
 *
 *   1. **borde de entrada**: el primer valor sale al instante, para que la tira
 *      reaccione en cuanto el dedo se mueve;
 *   2. **borde de salida**: el ultimo valor del gesto se emite **siempre**.
 *
 * La segunda es la razon de que este limitador exista tambien en el cliente,
 * y no solo en el servidor (que ya limita a `1000/LED_ROOM_BLE_MAX_UPDATES_PER_SECOND`
 * ms): el servidor no puede saber cual fue el ultimo valor de un gesto que
 * nunca le llego, y los mensajes ya enviados no se pueden "des-enviar". Sin
 * borde de salida, el usuario suelta el dedo y la tira se queda en un color
 * que no es el que eligio.
 *
 * No es duplicar una regla de negocio: en el cliente esto es coalescencia de
 * eventos de puntero (UX); en el servidor es proteccion del hardware, que debe
 * defenderse de N clientes y no fiarse de ninguno.
 *
 * @param emit  Que hacer con un valor que supera el filtro. Puede cambiar entre
 *              renders sin reiniciar el limitador.
 * @param intervalMs Milisegundos minimos entre emisiones.
 */
export function useThrottledValue<T>(
  emit: (value: T) => void,
  intervalMs: number,
): (value: T) => void {
  const emitRef = useRef(emit)
  const pendingRef = useRef<{ value: T } | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastEmitRef = useRef(Number.NEGATIVE_INFINITY)

  useEffect(() => {
    emitRef.current = emit
  })

  const flush = useCallback(() => {
    timerRef.current = null
    const pending = pendingRef.current
    if (pending === null) return

    pendingRef.current = null
    lastEmitRef.current = Date.now()
    emitRef.current(pending.value)
  }, [])

  // Un temporizador vivo tras desmontar emitiria sobre un socket que ya no
  // existe; el valor pendiente se descarta a proposito.
  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    },
    [],
  )

  return useCallback(
    (value: T) => {
      const now = Date.now()
      const elapsed = now - lastEmitRef.current

      if (timerRef.current === null && elapsed >= intervalMs) {
        lastEmitRef.current = now
        emitRef.current(value)
        return
      }

      // Ultimo valor gana: no hay cola. Una cola de 200 colores obsoletos es
      // justamente el problema que se quiere evitar.
      pendingRef.current = { value }
      if (timerRef.current === null) {
        timerRef.current = setTimeout(flush, Math.max(0, intervalMs - elapsed))
      }
    },
    [flush, intervalMs],
  )
}
