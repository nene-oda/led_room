import styles from './ControlNote.module.css'

export interface ControlNoteProps {
  /** Se enlaza al control con `aria-describedby`: por eso el id viene de fuera. */
  readonly id: string
  readonly children: string
}

/**
 * Explicacion de por que un control esta deshabilitado o limitado.
 *
 * Existe como pieza propia porque la regla se repite en todos los controles y
 * se incumple con facilidad: deshabilitar sin explicar deja al usuario sin
 * saber si el fallo es suyo, del dispositivo o de la red. Al ir enlazada por
 * `aria-describedby`, un lector de pantalla la anuncia junto al control en vez
 * de dejarla suelta en la pagina.
 */
export function ControlNote({ id, children }: ControlNoteProps) {
  return (
    <p id={id} className={styles.note}>
      {children}
    </p>
  )
}
