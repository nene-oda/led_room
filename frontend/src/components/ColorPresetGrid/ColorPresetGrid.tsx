import { useId } from 'react'

import styles from './ColorPresetGrid.module.css'
import { toHex, type RGBColor } from '../../domain/color'
import type { ColorPreset } from '../../domain/presets'
import { ControlNote } from '../ui/ControlNote'

export interface ColorPresetGridProps {
  readonly presets: readonly ColorPreset[]
  /** Color aplicado, para marcar cual de los presets coincide. */
  readonly current: RGBColor
  readonly disabled: boolean
  readonly disabledReason?: string | undefined
  readonly onSelect: (color: RGBColor) => void
}

/**
 * Rejilla de colores fijos.
 *
 * **No son escenas** (ver `domain/presets.ts`): son constantes del cliente y
 * pulsar una equivale a mover el selector hasta ese color. Por eso el color
 * elegido se escribe directamente por REST: es una intencion puntual, no un
 * arrastre.
 *
 * `aria-pressed` marca el preset que coincide con el color actual, de modo que
 * un lector de pantalla puede decir cual esta aplicado sin describir el color.
 */
export function ColorPresetGrid({
  presets,
  current,
  disabled,
  disabledReason,
  onSelect,
}: ColorPresetGridProps) {
  const noteId = useId()
  const headingId = useId()
  const currentHex = toHex(current)

  return (
    <section className={styles.presets} aria-labelledby={headingId}>
      <h2 id={headingId}>Colores rápidos</h2>

      <ul className={styles.grid}>
        {presets.map((preset) => {
          const hex = toHex(preset.color)
          return (
            <li key={hex}>
              <button
                type="button"
                className={styles.swatch}
                style={{ backgroundColor: hex }}
                aria-label={preset.name}
                aria-pressed={hex === currentHex}
                aria-describedby={disabledReason === undefined ? undefined : noteId}
                disabled={disabled}
                onClick={() => {
                  onSelect(preset.color)
                }}
              />
            </li>
          )
        })}
      </ul>

      {disabledReason !== undefined && <ControlNote id={noteId}>{disabledReason}</ControlNote>}
    </section>
  )
}
