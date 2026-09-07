import { useId, useState } from 'react'

import styles from '../ui/catalog.module.css'
import {
  NAME_MAX_LENGTH,
  defaultSceneOf,
  hasProfileErrors,
  includesScene,
  validateProfileDraft,
  withDefaultScene,
  withScene,
  type ProfileDraft,
} from '../../domain/profiles'
import type { Scene } from '../../domain/scenes'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'

export interface ProfileEditorProps {
  readonly initial: ProfileDraft
  readonly existing: boolean
  readonly saving: boolean
  /** Catalogo completo: un perfil se compone eligiendo entre lo que existe. */
  readonly scenes: readonly Scene[]
  readonly onSave: (draft: ProfileDraft) => void
  readonly onCancel: () => void
}

/**
 * Editor de un perfil: nombre, que escenas lo componen y cual activa.
 *
 * Dos columnas de marcas y no una lista con arrastre: **pertenecer al perfil**
 * y **ser la predeterminada** son dos hechos distintos, y una sola marca
 * obligaria a inventar reglas ("la primera manda") que el usuario no ve.
 *
 * El orden de las escenas es el del array, que es lo que el contrato de
 * escritura convierte en `position`. Reordenar no se ofrece todavia: hoy la
 * posicion solo sirve para desempatar la predeterminada, y esa se elige a mano.
 */
export function ProfileEditor({
  initial,
  existing,
  saving,
  scenes,
  onSave,
  onCancel,
}: ProfileEditorProps) {
  const [draft, setDraft] = useState<ProfileDraft>(initial)
  const headingId = useId()
  const nameId = useId()
  const nameErrorId = useId()
  const descriptionId = useId()
  const scenesErrorId = useId()
  const defaultName = useId()

  const errors = validateProfileDraft(draft)
  const blocked = hasProfileErrors(errors)
  const chosen = defaultSceneOf(draft)

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
        {existing ? 'Editar perfil' : 'Nuevo perfil'}
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
            setDraft({ ...draft, description: value === '' ? null : event.target.value })
          }}
        />
      </div>

      <fieldset className={styles.field ?? ''}>
        <legend>Escenas del perfil</legend>

        <ControlNote id={scenesErrorId}>
          {errors.scenes ??
            'Activar el perfil activa la escena marcada como predeterminada: es la misma operación, con los mismos errores.'}
        </ControlNote>

        {scenes.length === 0 ? (
          <p className={styles.empty ?? ''}>
            Todavía no hay escenas guardadas. Crea una en «Escenas» y vuelve aquí.
          </p>
        ) : (
          <ul className={styles.options ?? ''}>
            {scenes.map((scene) => {
              const included = includesScene(draft, scene.id)
              return (
                <li key={scene.id} className={styles.option ?? ''}>
                  <label>
                    <input
                      type="checkbox"
                      checked={included}
                      onChange={(event) => {
                        setDraft(withScene(draft, scene.id, event.target.checked))
                      }}
                    />
                    {scene.name}
                  </label>

                  <label>
                    <input
                      type="radio"
                      name={defaultName}
                      checked={included && chosen === scene.id}
                      // Solo se puede predeterminar lo que forma parte del
                      // perfil: el estado contrario no llega a existir.
                      disabled={!included}
                      onChange={() => {
                        setDraft(withDefaultScene(draft, scene.id))
                      }}
                    />
                    Predeterminada
                  </label>
                </li>
              )
            })}
          </ul>
        )}
      </fieldset>

      <div className={styles.actions ?? ''}>
        <Button
          busy={saving}
          disabled={blocked}
          describedBy={errors.scenes === undefined ? undefined : scenesErrorId}
          onClick={() => {
            onSave(draft)
          }}
        >
          {existing ? 'Guardar cambios' : 'Crear perfil'}
        </Button>
        <Button onClick={onCancel}>Cancelar</Button>
      </div>
    </form>
  )
}
