import { useId, useRef, type KeyboardEvent, type PointerEvent } from 'react'

import styles from './ColorPicker.module.css'
import { toHex, type RGBColor } from '../../domain/color'
import { hsvToRgb, rgbToHsv, HUE_MAX } from '../../domain/hsv'
import { ControlNote } from '../ui/ControlNote'

export interface ColorPickerProps {
  /**
   * Que color se esta eligiendo.
   *
   * Existe porque este control se usa en dos sitios con el mismo
   * comportamiento y distinto significado: el color de la tira y el color de un
   * paso de la paleta de un efecto. Duplicar el selector para cambiarle el
   * titulo habria dejado dos implementaciones del arrastre.
   */
  readonly label?: string | undefined
  readonly color: RGBColor
  readonly disabled: boolean
  readonly disabledReason?: string | undefined
  /** Un fotograma del gesto. Va por WebSocket y no persiste. */
  readonly onPreview: (color: RGBColor) => void
  /** Cierre del gesto. Va por REST y es lo unico que se guarda. */
  readonly onCommit: (color: RGBColor) => void
}

/** Paso de las flechas del teclado: 4° de tono y 4 % de saturacion. */
const HUE_STEP = 4
const SATURATION_STEP = 0.04

/**
 * Selector de color en dos dimensiones: **tono en X, saturacion en Y**.
 *
 * Tres decisiones que no son evidentes:
 *
 * 1. **El valor (V de HSV) se deja fijo en 1** y el brillo tiene su propio
 *    control. En este hardware el brillo es un canal aparte: mezclarlos haria
 *    que bajar el brillo cambiase el color enviado, y al reconectar la tira
 *    volveria a un color que el usuario no eligio.
 * 2. **No guarda estado propio.** La posicion del puntero se deriva del color
 *    que recibe; como quien lo usa aplica el valor local de inmediato, el
 *    arrastre se ve fluido sin duplicar el estado (que es lo que produce los
 *    saltos cuando el eco del servidor y el estado local discrepan).
 * 3. **Solo Pointer Events**, con `setPointerCapture`, y `touch-action: none`
 *    en el area: sin eso el navegador se queda con el gesto para hacer scroll o
 *    zoom, que es el fallo numero uno de este control en un movil.
 *
 * Este control no implica nada espacial: la tira muestra **un solo color a la
 * vez**. No hay degradados por LED que prometer.
 */
export function ColorPicker({
  label = 'Color',
  color,
  disabled,
  disabledReason,
  onPreview,
  onCommit,
}: ColorPickerProps) {
  const areaRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)
  const noteId = useId()
  const helpId = useId()
  const headingId = useId()

  const { h, s } = rgbToHsv(color)
  const hex = toHex(color)

  const colorAt = (event: PointerEvent<HTMLDivElement>): RGBColor | null => {
    const rect = areaRef.current?.getBoundingClientRect()
    // En jsdom (y antes del primer layout) el rectangulo es 0x0: sin esta
    // guarda saldria una division por cero y un color arbitrario.
    if (rect === undefined || rect.width <= 0 || rect.height <= 0) return null

    const x = unit((event.clientX - rect.left) / rect.width)
    const y = unit((event.clientY - rect.top) / rect.height)
    return hsvToRgb({ h: x * HUE_MAX, s: 1 - y, v: 1 })
  }

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (disabled) return

    draggingRef.current = true
    // Opcional: jsdom no lo implementa. Sin captura, sacar el dedo del area
    // rompe el arrastre en un movil real.
    event.currentTarget.setPointerCapture?.(event.pointerId)

    const next = colorAt(event)
    if (next !== null) onPreview(next)
  }

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return
    const next = colorAt(event)
    if (next !== null) onPreview(next)
  }

  const handlePointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    event.currentTarget.releasePointerCapture?.(event.pointerId)

    // El ultimo valor del gesto se persiste siempre, tambien si el puntero se
    // solto fuera del area.
    onCommit(colorAt(event) ?? color)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return

    const moved = move(event.key, h, s)
    if (moved === null) return

    // Las flechas se tratan como arrastre (no como intencion puntual): mantener
    // pulsada una tecla repite a ~30 Hz y cada repeticion seria una escritura.
    event.preventDefault()
    onPreview(hsvToRgb({ ...moved, v: 1 }))
  }

  return (
    <section className={styles.picker} aria-labelledby={headingId}>
      <h2 id={headingId}>{label}</h2>

      <div
        ref={areaRef}
        className={styles.area}
        role="group"
        aria-label={`Selector de ${label.toLowerCase()}`}
        aria-disabled={disabled}
        aria-describedby={disabledReason === undefined ? helpId : `${helpId} ${noteId}`}
        tabIndex={disabled ? -1 : 0}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
        onKeyDown={handleKeyDown}
      >
        <span
          className={styles.handle}
          style={{ left: `${String((h / HUE_MAX) * 100)}%`, top: `${String((1 - s) * 100)}%` }}
          aria-hidden="true"
        />
      </div>

      <p id={helpId} className={styles.help}>
        Arrastra para elegir el color; con el teclado, usa las flechas.
      </p>

      <p className={styles.value} role="status" aria-live="polite">
        Color actual: <span className={styles.swatch} style={{ backgroundColor: hex }} />
        {hex}
      </p>

      {disabledReason !== undefined && <ControlNote id={noteId}>{disabledReason}</ControlNote>}
    </section>
  )
}

function move(key: string, hue: number, saturation: number): { h: number; s: number } | null {
  switch (key) {
    case 'ArrowLeft':
      return { h: hue - HUE_STEP, s: saturation }
    case 'ArrowRight':
      return { h: hue + HUE_STEP, s: saturation }
    case 'ArrowUp':
      return { h: hue, s: Math.min(1, saturation + SATURATION_STEP) }
    case 'ArrowDown':
      return { h: hue, s: Math.max(0, saturation - SATURATION_STEP) }
    default:
      return null
  }
}

function unit(value: number): number {
  return Math.min(1, Math.max(0, value))
}
