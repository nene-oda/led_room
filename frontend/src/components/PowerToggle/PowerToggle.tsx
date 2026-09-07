import { useId } from 'react'

import { ControlNote } from '../ui/ControlNote'
import { Toggle } from '../ui/Toggle'

export interface PowerToggleProps {
  readonly on: boolean
  readonly disabled: boolean
  /** Por que no se puede usar. Obligatorio si `disabled`; se enlaza al control. */
  readonly disabledReason?: string | undefined
  readonly onChange: (on: boolean) => void
}

/**
 * Encendido de la tira.
 *
 * Reutiliza la primitiva `Toggle`, que no invierte su estado por su cuenta:
 * emite la intencion y espera el `on` que le devuelva quien la usa. Eso es lo
 * que permite que el interruptor vuelva atras solo si el servidor rechaza el
 * comando, en vez de quedarse mintiendo.
 *
 * El encendido no depende de ninguna capacidad: un dispositivo de luz que no se
 * pueda encender no seria un dispositivo de luz. Solo exige que haya enlace.
 */
export function PowerToggle({ on, disabled, disabledReason, onChange }: PowerToggleProps) {
  const noteId = useId()

  return (
    <div>
      <Toggle
        label={on ? 'Encendida' : 'Apagada'}
        checked={on}
        disabled={disabled}
        describedBy={disabledReason === undefined ? undefined : noteId}
        onChange={onChange}
      />
      {disabledReason !== undefined && <ControlNote id={noteId}>{disabledReason}</ControlNote>}
    </div>
  )
}
