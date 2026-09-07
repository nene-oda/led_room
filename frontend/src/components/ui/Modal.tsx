import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from 'react'

import styles from './Modal.module.css'
import { useScrollLock } from '../../hooks/useScrollLock'

export interface ModalProps {
  /** Titulo visible; tambien es el nombre accesible del dialogo. */
  readonly title: string
  /** Se pide cerrar: Escape, la X o el fondo. Quien lo usa decide si cierra. */
  readonly onClose: () => void
  /**
   * ¿Cierra un clic en el fondo?
   *
   * Por defecto si, porque es el gesto que todo el mundo espera. Se pone a
   * `false` cuando dentro hay un formulario con cambios sin guardar: un clic
   * accidental a dos centimetros del borde **no puede** costar lo que acabas de
   * escribir. Escape y la X siguen cerrando: son gestos deliberados, y quitar
   * Escape romperia lo que un dialogo tiene que hacer (WAI-ARIA APG).
   */
  readonly dismissOnBackdrop?: boolean | undefined
  readonly children: ReactNode
}

/**
 * Dialogo modal generico. **No sabe nada del dominio**: abre, cierra y presenta
 * lo que le den. Ni dispositivos, ni escenas, ni efectos, ni un `switch` por
 * tipo; si algun dia lo tuviera, estaria mal.
 *
 * Se monta **solo cuando esta abierto** (no recibe `open`): asi es imposible
 * representar "cerrado pero montado", y cada apertura estrena los hijos, que es
 * lo que hace que un editor empiece limpio en vez de recordar el borrador
 * anterior.
 *
 * ## Por que `<dialog>` nativo y no una capa a mano
 *
 * Un modal hecho a mano obliga a reimplementar cuatro cosas que la plataforma
 * ya hace bien: la **trampa de foco** (incluido el cursor virtual del lector de
 * pantalla, que un manejador de Tab no atrapa), **Escape**, la **capa superior**
 * —inmune a cualquier ancestro con `overflow`, `transform` o `z-index`, y aqui
 * el dialogo vive dentro de una rejilla— y el `::backdrop`. Todo eso son ~150
 * lineas sutiles que se rompen en silencio. `showModal()` las da gratis y,
 * ademas, marca el resto de la pagina como inerte de verdad.
 *
 * Sus asperezas conocidas se resuelven aqui, una sola vez:
 *
 *   - **Escape** dispara `cancel`; se escucha con `addEventListener` (no con
 *     `onCancel`, que no burbujea y depende de la delegacion de React) y se
 *     hace `preventDefault` para que el DOM nunca se cierre por su cuenta: la
 *     unica fuente de verdad de "esta abierto" es quien monta este componente.
 *   - **el clic en el fondo** llega como un clic sobre el propio `<dialog>`. Se
 *     distingue comparando el objetivo con el elemento, y para eso el dialogo no
 *     tiene relleno propio: todo el contenido va en un envoltorio interior. Se
 *     exige ademas que el gesto **empiece y acabe** en el fondo, para no cerrar
 *     cuando se selecciona texto y se suelta el raton fuera.
 *   - **la devolucion del foco** la hace este componente, no el navegador: al
 *     cerrar desmontamos el dialogo, y quitar del DOM un `<dialog>` abierto no
 *     ejecuta la restauracion de foco del estandar (el foco caeria en `body`).
 *   - **el scroll del fondo** no lo bloquea `<dialog>`: lo hace `useScrollLock`.
 *   - **jsdom no implementa `<dialog>`**: hay un doble de plataforma en
 *     `src/test/dialogPolyfill.ts`, con lo que emula y lo que no.
 */
export function Modal({ title, onClose, dismissOnBackdrop = true, children }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const backdropPressRef = useRef(false)
  const headingId = useId()

  useScrollLock()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) return

    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.showModal()

    return () => {
      // Cerrar antes de desmontar deja el elemento reutilizable si React lo
      // vuelve a montar (StrictMode monta, limpia y vuelve a montar).
      if (dialog.open) dialog.close()
      if (opener !== null && opener.isConnected) opener.focus()
    }
  }, [])

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) return

    const handleCancel = (event: Event) => {
      event.preventDefault()
      onClose()
    }

    dialog.addEventListener('cancel', handleCancel)
    return () => {
      dialog.removeEventListener('cancel', handleCancel)
    }
  }, [onClose])

  const handleMouseDown = (event: MouseEvent<HTMLDialogElement>) => {
    backdropPressRef.current = event.target === dialogRef.current
  }

  const handleClick = (event: MouseEvent<HTMLDialogElement>) => {
    const onBackdrop = backdropPressRef.current && event.target === dialogRef.current
    backdropPressRef.current = false
    if (onBackdrop && dismissOnBackdrop) onClose()
  }

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      // `role` y `aria-modal` son redundantes con un `<dialog>` abierto con
      // `showModal()`, pero no todas las combinaciones de navegador y lector de
      // pantalla mapean todavia la capa superior; explicitarlos no cuesta nada
      // y no depende de esa cadena.
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
      onMouseDown={handleMouseDown}
      onClick={handleClick}
    >
      {/* Envoltorio obligatorio: sin el, los huecos del propio dialogo
          contarian como fondo y un clic entre dos bloques lo cerraria. */}
      <div className={styles.panel}>
        <header className={styles.header}>
          <h2 id={headingId} className={styles.title}>
            {title}
          </h2>
          <button
            type="button"
            className={styles.close}
            aria-label={`Cerrar ${title}`}
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <div className={styles.body}>{children}</div>
      </div>
    </dialog>
  )
}
