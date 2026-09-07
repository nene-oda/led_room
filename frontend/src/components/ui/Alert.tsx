import styles from './Alert.module.css'

export interface AlertProps {
  readonly message: string
  readonly onDismiss: () => void
}

/**
 * Aviso de un fallo que ya ocurrio.
 *
 * `role="alert"` porque un rollback silencioso es peor que el propio fallo: el
 * control vuelve a su valor anterior y, sin esto, nadie sabria por que. Se
 * descarta a mano; no desaparece solo, para que no se pierda si el movil estaba
 * en el bolsillo.
 */
export function Alert({ message, onDismiss }: AlertProps) {
  return (
    <div className={styles.alert} role="alert">
      <span className={styles.message}>{message}</span>
      <button type="button" className={styles.dismiss} onClick={onDismiss}>
        Descartar
      </button>
    </div>
  )
}
