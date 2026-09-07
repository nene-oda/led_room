import styles from './Toggle.module.css'

export interface ToggleProps {
  /** Nombre accesible del interruptor; se renderiza como texto visible. */
  readonly label: string
  readonly checked: boolean
  readonly onChange: (checked: boolean) => void
  readonly disabled?: boolean | undefined
  /** Id del texto que explica por que el control esta deshabilitado. */
  readonly describedBy?: string | undefined
}

/**
 * Interruptor presentacional y controlado.
 *
 * `<button>` real con `role="switch"`: la activacion por Espacio/Intro, el foco
 * y el estado deshabilitado los aporta la plataforma, y `aria-checked` da la
 * semantica de interruptor. Un `div` con `onClick` obligaria a reimplementar
 * las tres cosas.
 *
 * No conoce la luz ni la red: emite el estado solicitado y espera que el
 * llamante le devuelva `checked` cuando el servidor lo confirme.
 */
export function Toggle({ label, checked, onChange, disabled = false, describedBy }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-describedby={describedBy}
      className={styles.toggle}
      disabled={disabled}
      onClick={() => {
        onChange(!checked)
      }}
    >
      <span className={styles.label}>{label}</span>
      <span className={styles.track} aria-hidden="true">
        <span className={styles.knob} />
      </span>
    </button>
  )
}
