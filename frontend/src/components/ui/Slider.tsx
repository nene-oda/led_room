import { useId } from 'react'

import styles from './Slider.module.css'

export interface SliderProps {
  /** Etiqueta visible, asociada al control con `htmlFor`. */
  readonly label: string
  readonly value: number
  readonly onChange: (value: number) => void
  /** Por defecto 0-100 entero: el brillo del dominio (ARCHITECTURE.md 3.3). */
  readonly min?: number | undefined
  readonly max?: number | undefined
  readonly step?: number | undefined
  /**
   * Texto que anuncia el lector de pantalla y que se muestra junto a la
   * etiqueta. Por defecto se formatea como porcentaje, coherente con el rango
   * por defecto; con otro rango hay que pasarlo.
   */
  readonly valueText?: string | undefined
  readonly disabled?: boolean | undefined
  /** Id del texto que explica por que el control esta deshabilitado. */
  readonly describedBy?: string | undefined
}

const DEFAULT_MIN = 0
const DEFAULT_MAX = 100
const DEFAULT_STEP = 1

/**
 * Slider presentacional y controlado.
 *
 * Se apoya en `<input type="range">` en lugar de reimplementar el arrastre: el
 * navegador aporta teclado (flechas, Inicio/Fin), semantica de `slider`,
 * captura del puntero y gestion tactil sin ramas separadas de raton y touch.
 * Un arrastre propio solo se justifica donde el control no existe en la
 * plataforma, como el area 2D del futuro selector de color.
 *
 * No sabe nada de brillo, de HTTP ni del dispositivo: emite numeros. El
 * limitado de frecuencia vive en el hook que lo consume.
 */
export function Slider({
  label,
  value,
  onChange,
  min = DEFAULT_MIN,
  max = DEFAULT_MAX,
  step = DEFAULT_STEP,
  valueText,
  disabled = false,
  describedBy,
}: SliderProps) {
  const inputId = useId()
  const text = valueText ?? `${value} %`

  return (
    <div className={styles.slider}>
      <div className={styles.header}>
        <label className={styles.label} htmlFor={inputId}>
          {label}
        </label>
        {/* aria-hidden: el mismo dato ya viaja en aria-valuetext y duplicarlo
            hace que el lector lo anuncie dos veces. */}
        <span className={styles.value} aria-hidden="true">
          {text}
        </span>
      </div>
      <input
        id={inputId}
        className={styles.input}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-valuetext={text}
        aria-describedby={describedBy}
        onChange={(event) => {
          onChange(event.target.valueAsNumber)
        }}
      />
    </div>
  )
}
