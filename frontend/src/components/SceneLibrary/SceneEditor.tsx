import { useId, useState } from 'react'

import { SceneTargetFields } from './SceneTargetFields'
import styles from '../ui/catalog.module.css'
import type { Effect } from '../../domain/effects'
import {
  NAME_MAX_LENGTH,
  hasSceneErrors,
  usedDevices,
  validateSceneDraft,
  withAddedTarget,
  withRemovedTarget,
  withSceneTarget,
  type SceneDraft,
} from '../../domain/scenes'
import type { RegisteredDevice } from '../../state/lightStateContext'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'
import { Toggle } from '../ui/Toggle'

export interface SceneEditorProps {
  /** Punto de partida. La copia de trabajo vive aqui dentro. */
  readonly initial: SceneDraft
  /** `true` al editar una existente: solo cambia el titulo y el boton. */
  readonly existing: boolean
  readonly saving: boolean
  readonly devices: readonly RegisteredDevice[]
  readonly effects: readonly Effect[]
  readonly onSave: (draft: SceneDraft) => void
  readonly onCancel: () => void
}

/**
 * Editor de una escena.
 *
 * El borrador es estado **local** del formulario: hasta que se guarda no existe
 * en el servidor y no lo necesita nadie mas. El padre lo reinicia con `key`, no
 * con un efecto de sincronizacion. Misma decision que en el editor de efectos.
 *
 * Lo que este formulario tiene que dejar claro y no puede maquillar:
 *
 * 1. **La escena referencia efectos**; el color fijo es un atajo que crea uno.
 *    Lo cuenta cada objetivo, con el nombre del efecto que va a aparecer.
 * 2. **Activar es todo o nada**, y hoy el servidor mantiene un solo enlace: una
 *    escena con un dispositivo que no es el conectado no se activa a medias, se
 *    rechaza entera. Se avisa aqui, que es donde se construye ese caso.
 */
export function SceneEditor({
  initial,
  existing,
  saving,
  devices,
  effects,
  onSave,
  onCancel,
}: SceneEditorProps) {
  const [draft, setDraft] = useState<SceneDraft>(initial)
  const headingId = useId()
  const nameId = useId()
  const nameErrorId = useId()
  const descriptionId = useId()
  const targetsErrorId = useId()

  const errors = validateSceneDraft(draft)
  const blocked = hasSceneErrors(errors)
  const taken = usedDevices(draft)
  const free = devices.filter((device) => !taken.has(device.id))

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
        {existing ? 'Editar escena' : 'Nueva escena'}
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
        <label htmlFor={descriptionId}>Descripción (opcional)</label>
        <input
          id={descriptionId}
          className={styles.input ?? ''}
          type="text"
          value={draft.description ?? ''}
          onChange={(event) => {
            const value = event.target.value.trim()
            // Cadena vacia -> `null`: el contrato distingue "sin descripcion" de
            // "descripcion vacia", y guardar la segunda no significa nada.
            setDraft({ ...draft, description: value === '' ? null : event.target.value })
          }}
        />
      </div>

      <Toggle
        label="Escena rápida (favorita)"
        checked={draft.isFavorite}
        onChange={(checked) => {
          setDraft({ ...draft, isFavorite: checked })
        }}
      />

      <h4 className={styles.groupTitle ?? ''}>Qué reproduce</h4>

      <ControlNote id={targetsErrorId}>
        {errors.targets ??
          'Se activa entera o no se activa: si alguno de sus dispositivos no es el que está conectado, el servidor la rechaza sin reproducir nada.'}
      </ControlNote>

      {draft.targets.map((target, index) => (
        <SceneTargetFields
          // Los objetivos no tienen identidad propia: la clave real es el
          // dispositivo, que es justo lo que el servidor exige que no se repita.
          key={target.deviceId}
          target={target}
          devices={devices}
          takenDeviceIds={new Set([...taken].filter((id) => id !== target.deviceId))}
          effects={effects}
          removable={draft.targets.length > 1}
          onChange={(next) => {
            setDraft(withSceneTarget(draft, index, next))
          }}
          onRemove={() => {
            setDraft(withRemovedTarget(draft, index))
          }}
        />
      ))}

      {/* Deshabilitado cuando ya no queda ningun dispositivo libre: dos
          objetivos al mismo dispositivo son un 422, asi que ese estado no
          llega a poder construirse. */}
      <Button
        disabled={free.length === 0}
        describedBy={targetsErrorId}
        onClick={() => {
          const next = free[0]
          if (next !== undefined) setDraft(withAddedTarget(draft, next.id))
        }}
      >
        Añadir dispositivo
      </Button>

      <div className={styles.actions ?? ''}>
        <Button busy={saving} disabled={blocked} onClick={() => { onSave(draft) }}>
          {existing ? 'Guardar cambios' : 'Crear escena'}
        </Button>
        <Button onClick={onCancel}>Cancelar</Button>
      </div>
    </form>
  )
}
