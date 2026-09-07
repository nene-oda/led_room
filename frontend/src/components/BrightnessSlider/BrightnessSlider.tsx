import { useId } from 'react'

import { BRIGHTNESS_MAX, BRIGHTNESS_MIN, clampBrightness } from '../../domain/light'
import { ControlNote } from '../ui/ControlNote'
import { Slider } from '../ui/Slider'

export interface BrightnessSliderProps {
  /** Entero 0-100 (ARCHITECTURE.md 3.3). La escala del hardware no llega aqui. */
  readonly value: number
  readonly disabled: boolean
  readonly disabledReason?: string | undefined
  readonly onChange: (value: number) => void
}

/**
 * Brillo de la tira.
 *
 * Cada cambio es un fotograma de un arrastre, no una intencion puntual: quien
 * lo recibe lo manda por WebSocket limitado y cierra el gesto con una escritura
 * REST. Este componente no lo sabe ni le corresponde saberlo; su unico trabajo
 * es emitir enteros validos.
 */
export function BrightnessSlider({
  value,
  disabled,
  disabledReason,
  onChange,
}: BrightnessSliderProps) {
  const noteId = useId()

  return (
    <div>
      <Slider
        label="Brillo"
        value={clampBrightness(value)}
        min={BRIGHTNESS_MIN}
        max={BRIGHTNESS_MAX}
        step={1}
        disabled={disabled}
        describedBy={disabledReason === undefined ? undefined : noteId}
        onChange={(next) => {
          onChange(clampBrightness(next))
        }}
      />
      {disabledReason !== undefined && <ControlNote id={noteId}>{disabledReason}</ControlNote>}
    </div>
  )
}
