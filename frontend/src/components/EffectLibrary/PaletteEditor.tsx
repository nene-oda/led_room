import { useId, useState } from 'react'

import styles from './EffectLibrary.module.css'
import catalog from '../ui/catalog.module.css'
import { toHex, type RGBColor } from '../../domain/color'
import type { EffectStep } from '../../domain/effects'
import { ColorPicker } from '../ColorPicker/ColorPicker'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'

export interface PaletteEditorProps {
  readonly steps: readonly EffectStep[]
  readonly canAdd: boolean
  readonly canRemove: boolean
  /** Por que la paleta no vale todavia. Se enlaza a la lista de colores. */
  readonly error?: string | undefined
  readonly onChangeColor: (index: number, color: RGBColor) => void
  readonly onAdd: () => void
  readonly onRemove: (index: number) => void
}

/**
 * La paleta de un efecto: la lista de colores por la que pasa.
 *
 * **Es lo que distingue a dos efectos del mismo tipo.** `Sunset` y `Cyberpunk`
 * son los dos `SMOOTH_CYCLE`; lo unico que cambia es esto.
 *
 * Reutiliza `ColorPicker` para elegir cada color, con su etiqueta cambiada. Es
 * el mismo control de siempre y **no manda nada al dispositivo**: aqui edita un
 * valor del formulario, y lo que se ve en la tira solo cambia cuando el efecto
 * se guarda y se reproduce.
 *
 * El indice seleccionado se **deriva** en cada render en vez de sincronizarse
 * con un efecto: al quitar el ultimo color, recortarlo aqui evita el fotograma
 * intermedio en el que la seleccion apunta a un paso que ya no existe.
 */
export function PaletteEditor({
  steps,
  canAdd,
  canRemove,
  error,
  onChangeColor,
  onAdd,
  onRemove,
}: PaletteEditorProps) {
  const [requested, setRequested] = useState(0)
  const errorId = useId()
  const headingId = useId()

  const selected = Math.min(requested, steps.length - 1)
  const current = steps[selected]

  return (
    <section className={styles.palette ?? ''} aria-labelledby={headingId}>
      <h3 id={headingId} className={catalog.groupTitle ?? ''}>
        Paleta
      </h3>

      <ul className={styles.swatches ?? ''} aria-describedby={error === undefined ? undefined : errorId}>
        {steps.map((step, index) => {
          const hex = toHex(step.color)
          return (
            <li key={`${String(index)}-${hex}`}>
              <button
                type="button"
                className={styles.swatch ?? ''}
                style={{ backgroundColor: hex }}
                // Nombre completo: media docena de botones sin texto visible
                // necesitan distinguirse al navegar con lector de pantalla.
                aria-label={`Color ${String(index + 1)} de la paleta: ${hex}`}
                aria-pressed={index === selected}
                onClick={() => {
                  setRequested(index)
                }}
              />
            </li>
          )
        })}
      </ul>

      {error !== undefined && <ControlNote id={errorId}>{error}</ControlNote>}

      <div className={catalog.actions ?? ''}>
        <Button disabled={!canAdd} onClick={onAdd}>
          Añadir color
        </Button>
        <Button
          disabled={!canRemove}
          ariaLabel={`Quitar el color ${String(selected + 1)} de la paleta`}
          onClick={() => {
            onRemove(selected)
          }}
        >
          Quitar color
        </Button>
      </div>

      {current !== undefined && (
        <ColorPicker
          label={`Color ${String(selected + 1)} de la paleta`}
          color={current.color}
          disabled={false}
          // Las dos devoluciones hacen lo mismo porque aqui no hay gesto que
          // repartir entre canales: nada viaja al dispositivo mientras se edita.
          onPreview={(color) => {
            onChangeColor(selected, color)
          }}
          onCommit={(color) => {
            onChangeColor(selected, color)
          }}
        />
      )}
    </section>
  )
}
