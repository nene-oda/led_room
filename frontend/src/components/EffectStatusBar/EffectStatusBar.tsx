import styles from './EffectStatusBar.module.css'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

/** Efecto en curso. `name` es `null` mientras el catalogo no se ha cargado. */
export interface RunningEffectView {
  readonly id: string
  readonly name: string | null
}

export interface EffectStatusBarProps {
  readonly running: RunningEffectView | null
  /** Nombre del efecto que un comando manual acaba de detener, si lo hubo. */
  readonly stoppedByCommand: { readonly name: string | null } | null
  /** Hay una orden de parada en curso. */
  readonly busy: boolean
  readonly onStop: (effectId: string) => void
}

/**
 * Que efecto esta sonando, siempre a la vista.
 *
 * Es una tarjeta propia, y a proposito **no** vive dentro del dialogo de
 * efectos: es la unica pieza que explica por que la tira cambia sola, y
 * esconderla detras de un clic dejaria al usuario mirando una luz que se mueve
 * sin saber quien la mueve. Por eso esta junto a los controles manuales, que
 * son justo los que la detienen.
 *
 * Se titula «Efecto en curso» y no «Efecto» para no confundirla con la tarjeta
 * «Efectos» de la rejilla de gestion: aquella guarda el catalogo, esta dice que
 * esta sonando ahora.
 *
 * Dice ademas lo que el servidor hace y la UI no puede impedir: **un comando
 * manual cancela el efecto**. Se anuncia antes (mientras suena) y se confirma
 * despues (cuando ya lo detuvo), porque un control que reacciona distinto de lo
 * esperado sin avisar se siente como un fallo.
 *
 * Es la **unica region viva** de los efectos: la lista no lleva otra, para que
 * arrancar uno no produzca dos anuncios seguidos.
 */
export function EffectStatusBar({ running, stoppedByCommand, busy, onStop }: EffectStatusBarProps) {
  return (
    <Card title="Efecto en curso">
      <div className={styles.row ?? ''}>
        <p className={styles.text ?? ''} role="status" aria-live="polite">
          {running !== null && (
            <span
              className={`${styles.dot ?? ''} ${styles.running ?? ''}`}
              aria-hidden="true"
            />
          )}
          {narrate(running, stoppedByCommand)}
        </p>

        {running !== null && (
          <Button
            busy={busy}
            ariaLabel={
              running.name === null ? 'Detener el efecto' : `Detener el efecto ${running.name}`
            }
            onClick={() => {
              onStop(running.id)
            }}
          >
            Detener
          </Button>
        )}
      </div>
    </Card>
  )
}

const MANUAL_WARNING =
  'Si cambias el color, el brillo o el encendido, el efecto se detendrá.'

function narrate(
  running: RunningEffectView | null,
  stoppedByCommand: { readonly name: string | null } | null,
): string {
  if (running !== null) {
    const subject = running.name === null ? 'Hay un efecto en marcha' : `En marcha: «${running.name}»`
    return `${subject}. ${MANUAL_WARNING}`
  }

  if (stoppedByCommand !== null) {
    const subject =
      stoppedByCommand.name === null ? 'El efecto se detuvo' : `«${stoppedByCommand.name}» se detuvo`
    return `${subject} porque enviaste un comando manual: el color, el brillo y el encendido cancelan el efecto en curso.`
  }

  return 'No hay ningún efecto en marcha.'
}
