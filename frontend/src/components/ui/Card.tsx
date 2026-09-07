import { useId, type ReactNode } from 'react'

import styles from './Card.module.css'

export interface CardProps {
  /** Titulo visible; tambien es el nombre accesible de la region. */
  readonly title: string
  /** Dato de estado corto junto al titulo: cuantos hay, que esta puesto. */
  readonly summary?: string | undefined
  readonly children: ReactNode
}

/**
 * Tarjeta de la pantalla principal: una region con titulo, un dato de estado y
 * su contenido.
 *
 * Es el **unico** cromo de tarjeta de la aplicacion. Sustituye al antiguo
 * `Panel` (un `<details>` plegable): la pantalla dejo de ser una columna larga
 * que se recorre plegando y desplegando, y paso a ser una rejilla donde cada
 * tarjeta se lee de un vistazo. No conviven los dos —el `Panel` se borro— para
 * que no haya dos piezas que hacen casi lo mismo.
 *
 * Solo presenta. Las tarjetas cuya tarea secundaria se abre en un dialogo usan
 * `ModalCard`, que es esta misma tarjeta mas el boton y el modal.
 */
export function Card({ title, summary, children }: CardProps) {
  const headingId = useId()

  return (
    <section className={styles.card} aria-labelledby={headingId}>
      <header className={styles.header}>
        <h2 id={headingId} className={styles.title}>
          {title}
        </h2>
        {summary !== undefined && <p className={styles.summary}>{summary}</p>}
      </header>

      <div className={styles.body}>{children}</div>
    </section>
  )
}
