import { useEffect, useState } from 'react'

/** Un segundo. La barra de progreso no necesita mas resolucion que la que dice. */
const TICK_MS = 1000

/**
 * Segundos completos transcurridos desde que `active` paso a ser cierto.
 *
 * Existe para poder dibujar progreso **contra una cota conocida** —lo que el
 * servidor declara que tarda un escaneo— en vez de un giro indeterminado que no
 * responde a "¿cuanto falta?".
 *
 * Se apoya en la hora real y no en contar ticks: un movil que suspende la
 * pestaña deja de ejecutar el intervalo, y un contador incremental se quedaria
 * corto justo cuando mas se nota.
 *
 * Vuelve a cero al desactivarse, de modo que el siguiente arranque no enseña ni
 * un fotograma del tiempo del anterior.
 */
export function useElapsedSeconds(active: boolean): number {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!active) return

    const startedAt = Date.now()
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / TICK_MS))
    }, TICK_MS)

    return () => {
      clearInterval(id)
      // El reinicio va en la limpieza y no en el cuerpo del efecto: asi el
      // siguiente arranque parte de cero sin que un `setState` sincrono en el
      // efecto encadene renders (react-hooks/set-state-in-effect).
      setElapsed(0)
    }
  }, [active])

  // Fuera de una cuenta activa no hay tiempo transcurrido que contar.
  return active ? elapsed : 0
}
