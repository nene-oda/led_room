import type { ReactNode } from 'react'

import styles from './Button.module.css'

export interface ButtonProps {
  readonly children: ReactNode
  readonly onClick: () => void
  readonly disabled?: boolean | undefined
  /**
   * Nombre accesible completo.
   *
   * Necesario en las listas, donde media docena de botones dicen "Conectar" y
   * el texto visible por si solo no distingue a cual pertenece cada uno.
   */
  readonly ariaLabel?: string | undefined
  /** Hay una operacion en curso: deshabilita y lo anuncia con `aria-busy`. */
  readonly busy?: boolean | undefined
  /**
   * Boton de dos estados (`aria-pressed`).
   *
   * Para preferencias que se aplican al instante y no viajan a ningun sitio. Un
   * `role="switch"` es para ajustes con estado propio; usarlo aqui haria que un
   * lector de pantalla anunciara como interruptor del dispositivo algo que solo
   * cambia lo que se ve.
   */
  readonly pressed?: boolean | undefined
  /**
   * Id del texto que explica por que el boton esta deshabilitado.
   *
   * Existe por la misma regla que en `Slider` y `Toggle`: deshabilitar sin
   * explicar deja al usuario sin saber si el fallo es suyo, del dispositivo o
   * de la red. Cuando el motivo es el mismo para varios botones, se escribe una
   * vez y todos apuntan a el.
   */
  readonly describedBy?: string | undefined
  /**
   * Este boton representa lo que esta puesto ahora mismo (`aria-current`).
   *
   * No es `pressed`: un interruptor de dos estados se puede desmarcar, y
   * activar una escena no tiene marcha atras -- se activa otra. `aria-current`
   * dice justo eso, "de esta lista, este es el vigente", que es lo que un
   * lector de pantalla tiene que anunciar.
   */
  readonly current?: boolean | undefined
}

/**
 * Boton de accion de la aplicacion.
 *
 * Existe para que el objetivo tactil de 44px y el estilo del borde salgan de un
 * solo sitio: estaban copiados en cada control que necesitaba un boton, y la
 * siguiente copia habria acabado con su propio radio y su propio gris. No tiene
 * variantes: el dia que haga falta una segunda, sera un componente con su
 * propio nombre y no un `variant` mas.
 */
export function Button({
  children,
  onClick,
  disabled,
  ariaLabel,
  busy = false,
  pressed,
  describedBy,
  current,
}: ButtonProps) {
  return (
    <button
      type="button"
      className={styles.button}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
      aria-busy={busy || undefined}
      aria-pressed={pressed}
      aria-current={current === true ? 'true' : undefined}
      disabled={disabled === true || busy}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
