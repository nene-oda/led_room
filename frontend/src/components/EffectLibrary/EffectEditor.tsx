import { useId, useState } from 'react'

import { PaletteEditor } from './PaletteEditor'
import styles from '../ui/catalog.module.css'
import {
  EFFECT_TYPES,
  EFFECT_TYPE_SPECS,
  NAME_MAX_LENGTH,
  SPEED_MAX,
  SPEED_MIN,
  TRANSITION_MAX_MS,
  TRANSITION_STEP_MS,
  canAddStep,
  canRemoveStep,
  formatSeconds,
  formatSpeedFactor,
  hasErrors,
  isEffectType,
  transitionDurationMs,
  validateEffectDraft,
  withAddedStep,
  withBrightness,
  withEffectType,
  withRemovedStep,
  withStepColor,
  type EffectDraft,
} from '../../domain/effects'
import { BRIGHTNESS_MAX, BRIGHTNESS_MIN } from '../../domain/light'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'
import { Slider } from '../ui/Slider'
import { Toggle } from '../ui/Toggle'

export interface EffectEditorProps {
  /** Punto de partida. La copia de trabajo vive aqui dentro. */
  readonly initial: EffectDraft
  /** `true` al editar uno existente: solo cambia el titulo y el boton. */
  readonly existing: boolean
  readonly saving: boolean
  readonly onSave: (draft: EffectDraft) => void
  readonly onCancel: () => void
}

/**
 * Editor de un efecto.
 *
 * Dos ideas que la pantalla tiene que dejar claras porque el modelo del backend
 * las tiene y una UI descuidada las borra:
 *
 * 1. **Tipo y paleta son cosas distintas.** El tipo es el algoritmo (los cuatro
 *    que tienen renderer); la paleta son los colores. Los efectos "con nombre"
 *    no son tipos: son ciclos suaves con paletas distintas.
 * 2. **La velocidad es un multiplicador, no una duracion.** Por eso al lado del
 *    control se lee siempre la duracion resultante: quien ve "velocidad 100" no
 *    debe pensar "100 ms".
 *
 * El borrador es estado **local** del formulario: hasta que se guarda no existe
 * en el servidor y no lo necesita nadie mas. El padre lo reinicia con `key`, no
 * con un efecto de sincronizacion.
 */
export function EffectEditor({ initial, existing, saving, onSave, onCancel }: EffectEditorProps) {
  const [draft, setDraft] = useState<EffectDraft>(initial)
  const nameId = useId()
  const nameErrorId = useId()
  const typeId = useId()
  const typeHelpId = useId()
  const speedHelpId = useId()
  const loopNoteId = useId()
  const brightnessErrorId = useId()
  const headingId = useId()

  const spec = EFFECT_TYPE_SPECS[draft.type]
  const errors = validateEffectDraft(draft)
  const blocked = hasErrors(errors)

  return (
    <form
      className={styles.editor ?? ''}
      aria-labelledby={headingId}
      onSubmit={(event) => {
        event.preventDefault()
        if (!blocked) onSave(draft)
      }}
    >
      <h3 id={headingId} className={styles.groupTitle ?? ''}>
        {existing ? 'Editar efecto' : 'Nuevo efecto'}
      </h3>

      <div className={styles.field ?? ''}>
        <label htmlFor={nameId}>Nombre</label>
        <input
          id={nameId}
          className={styles.input ?? ''}
          type="text"
          value={draft.name}
          maxLength={NAME_MAX_LENGTH}
          aria-describedby={errors.name === undefined ? undefined : nameErrorId}
          aria-invalid={errors.name !== undefined}
          onChange={(event) => {
            setDraft({ ...draft, name: event.target.value })
          }}
        />
        {errors.name !== undefined && <ControlNote id={nameErrorId}>{errors.name}</ControlNote>}
      </div>

      <div className={styles.field ?? ''}>
        <label htmlFor={typeId}>Tipo</label>
        <select
          id={typeId}
          className={styles.input ?? ''}
          value={draft.type}
          aria-describedby={typeHelpId}
          onChange={(event) => {
            const { value } = event.target
            // La paleta se adapta a las cotas del tipo nuevo en el dominio: sin
            // eso, pasar un ciclo de cuatro colores a «Fijo» dejaria un
            // borrador que el servidor rechazaria con un 422.
            if (isEffectType(value)) setDraft(withEffectType(draft, value))
          }}
        >
          {EFFECT_TYPES.map((type) => (
            <option key={type} value={type}>
              {EFFECT_TYPE_SPECS[type].label}
            </option>
          ))}
        </select>
        <p id={typeHelpId} className={styles.help ?? ''}>
          {spec.summary} El tipo es el algoritmo; los colores los pone la paleta:
          dos efectos con el mismo tipo y distinta paleta son dos efectos
          distintos.
        </p>
      </div>

      <PaletteEditor
        steps={draft.steps}
        canAdd={canAddStep(draft)}
        canRemove={canRemoveStep(draft)}
        error={errors.palette}
        onChangeColor={(index, color) => {
          setDraft(withStepColor(draft, index, color))
        }}
        onAdd={() => {
          setDraft(withAddedStep(draft))
        }}
        onRemove={(index) => {
          setDraft(withRemovedStep(draft, index))
        }}
      />

      <Slider
        label="Duración de la transición"
        value={draft.transitionMs}
        min={0}
        max={TRANSITION_MAX_MS}
        step={TRANSITION_STEP_MS}
        valueText={formatSeconds(draft.transitionMs)}
        onChange={(value) => {
          setDraft({ ...draft, transitionMs: value })
        }}
      />

      <div>
        <Slider
          label="Velocidad"
          value={draft.speed}
          min={SPEED_MIN}
          max={SPEED_MAX}
          step={1}
          valueText={`${String(draft.speed)} (${formatSpeedFactor(draft.speed)})`}
          describedBy={speedHelpId}
          onChange={(value) => {
            setDraft({ ...draft, speed: value })
          }}
        />
        {/* Sin esto, «velocidad 100» se lee como una duracion. La autoridad la
            tiene la duracion de la transicion; la velocidad la multiplica. */}
        <p id={speedHelpId} className={styles.help ?? ''}>
          La velocidad multiplica la duración: 0 la duplica, 50 la deja igual y
          100 la reduce a la mitad. Cada transición durará{' '}
          {formatSeconds(transitionDurationMs(draft))}.
        </p>
      </div>

      <Slider
        label={spec.brightnessEnvelope ? 'Brillo máximo' : 'Brillo'}
        value={draft.maxBrightness}
        min={BRIGHTNESS_MIN}
        max={BRIGHTNESS_MAX}
        step={1}
        describedBy={errors.brightness === undefined ? undefined : brightnessErrorId}
        onChange={(value) => {
          setDraft(withBrightness(draft, 'max', value))
        }}
      />

      {/* Solo donde significa algo: en `PULSE` y `BREATH` el brillo va y viene
          entre los dos extremos; en los demas tipos no hay envolvente que
          describir y un segundo control seria un adorno sin efecto. */}
      {spec.brightnessEnvelope && (
        <Slider
          label="Brillo mínimo"
          value={draft.minBrightness}
          min={BRIGHTNESS_MIN}
          max={BRIGHTNESS_MAX}
          step={1}
          describedBy={errors.brightness === undefined ? undefined : brightnessErrorId}
          onChange={(value) => {
            setDraft(withBrightness(draft, 'min', value))
          }}
        />
      )}

      {errors.brightness !== undefined && (
        <ControlNote id={brightnessErrorId}>{errors.brightness}</ControlNote>
      )}

      <div>
        <Toggle
          label="Repetir en bucle"
          checked={draft.loop}
          disabled={!spec.loopable}
          describedBy={spec.loopable ? undefined : loopNoteId}
          onChange={(loop) => {
            setDraft({ ...draft, loop })
          }}
        />
        {!spec.loopable && (
          <ControlNote id={loopNoteId}>
            {`«${spec.label}» no se repite: repetir un color fijo solo gastaría escrituras en el dispositivo.`}
          </ControlNote>
        )}
      </div>

      <div className={styles.actions ?? ''}>
        {/* Deshabilitado solo cuando hay un motivo escrito junto al campo que
            lo provoca: deshabilitar sin explicar deja al usuario adivinando. */}
        <Button busy={saving} disabled={blocked} onClick={() => onSave(draft)}>
          {existing ? 'Guardar cambios' : 'Crear efecto'}
        </Button>
        <Button onClick={onCancel}>Cancelar</Button>
      </div>
    </form>
  )
}
