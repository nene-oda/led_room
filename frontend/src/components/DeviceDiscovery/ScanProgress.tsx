import styles from './DeviceDiscovery.module.css'

export interface ScanProgressProps {
  /** Segundos que lleva el escaneo en curso. */
  readonly elapsedSeconds: number
  /** Lo maximo que el servidor dice que puede tardar. */
  readonly timeoutSeconds: number
}

/**
 * Cuanto lleva buscando, medido contra la cota que declara el servidor.
 *
 * ## Por que una barra determinada y no un giro indeterminado
 *
 * Un indicador indeterminado solo dice "sigo vivo". Aqui se conoce el techo del
 * escaneo (`scan_timeout_seconds`), asi que se puede responder a la pregunta
 * que de verdad se hace el usuario —¿cuanto falta?— y eso es justo lo que una
 * barra determinada comunica y un giro no.
 *
 * ## Y por que deja de serlo al llegar al final
 *
 * La barra mide **tiempo transcurrido frente al maximo anunciado**, no trabajo
 * completado: el escaneo puede acabar mucho antes, y de hecho suele hacerlo. Por
 * eso llegar al extremo no significa "casi listo". Si el servidor tarda mas que
 * su propio maximo, quedarse clavada en el 100% mientras se sigue esperando
 * seria una promesa falsa, asi que en ese momento **suelta el porcentaje**
 * (`aria-valuenow` desaparece, que es como ARIA expresa "indeterminado") y pasa
 * al recorrido continuo, que solo afirma que la operacion sigue en curso.
 *
 * El anuncio hablado no vive aqui: lo lleva la region viva del panel, que dice
 * el estado en palabras. Esto es su equivalente visual, no una segunda voz.
 */
export function ScanProgress({ elapsedSeconds, timeoutSeconds }: ScanProgressProps) {
  const overdue = elapsedSeconds >= timeoutSeconds
  const percent = overdue ? 100 : Math.round((elapsedSeconds / timeoutSeconds) * 100)

  return (
    <div
      className={styles.progress ?? ''}
      role="progressbar"
      aria-label="Progreso del escaneo"
      // Sin `aria-valuenow` cuando ya no se puede prometer un porcentaje: es la
      // forma estandar de declarar un progreso indeterminado.
      {...(overdue
        ? {}
        : {
            'aria-valuemin': 0,
            'aria-valuemax': timeoutSeconds,
            'aria-valuenow': elapsedSeconds,
            'aria-valuetext': `${String(elapsedSeconds)} s de un máximo de ${String(timeoutSeconds)} s`,
          })}
    >
      {overdue ? (
        <span className={styles.sweep ?? ''} />
      ) : (
        <span className={styles.fill ?? ''} style={{ width: `${String(percent)}%` }} />
      )}
    </div>
  )
}
