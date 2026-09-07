import { useId } from 'react'

import styles from '../ui/catalog.module.css'
import type { Effect } from '../../domain/effects'
import {
  newTargetDraft,
  staticEffectName,
  type SceneTargetDraft,
} from '../../domain/scenes'
import type { RegisteredDevice } from '../../state/lightStateContext'
import { ColorPicker } from '../ColorPicker/ColorPicker'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'

export interface SceneTargetFieldsProps {
  readonly target: SceneTargetDraft
  /** Dispositivos dados de alta, para poder elegir a cual apunta el objetivo. */
  readonly devices: readonly RegisteredDevice[]
  /** Dispositivos que ya ocupan OTRO objetivo: repetir uno es un 422. */
  readonly takenDeviceIds: ReadonlySet<string>
  readonly effects: readonly Effect[]
  readonly removable: boolean
  readonly onChange: (target: SceneTargetDraft) => void
  readonly onRemove: () => void
}

/**
 * Un dispositivo de la escena y lo que reproduce.
 *
 * Aqui se resuelve la unica parte incomoda del contrato: **una escena no
 * guarda un color, guarda una referencia a un efecto**. En vez de obligar al
 * usuario a crear antes un efecto `STATIC` de un paso —que es lo que el backend
 * exige—, se le ofrece elegir un color y se le dice, con el nombre exacto, que
 * ese efecto se va a guardar en su biblioteca. El atajo se ofrece; la
 * normalizacion no se esconde.
 *
 * El selector de color de aqui **no toca el dispositivo**: solo edita el
 * borrador. Es el mismo componente que el del control manual porque el gesto es
 * el mismo, pero sus dos salidas (arrastre y cierre) acaban en el estado del
 * formulario, no en el cable.
 */
export function SceneTargetFields({
  target,
  devices,
  takenDeviceIds,
  effects,
  removable,
  onChange,
  onRemove,
}: SceneTargetFieldsProps) {
  const deviceId = useId()
  const sourceName = useId()
  const effectId = useId()
  const noteId = useId()

  const known = devices.some((device) => device.id === target.deviceId)
  const options = devices.filter(
    (device) => device.id === target.deviceId || !takenDeviceIds.has(device.id),
  )

  return (
    <div className={styles.editor ?? ''}>
      <div className={styles.field ?? ''}>
        <label htmlFor={deviceId}>Dispositivo</label>
        <select
          id={deviceId}
          className={styles.input ?? ''}
          value={target.deviceId}
          onChange={(event) => {
            onChange({ ...target, deviceId: event.target.value })
          }}
        >
          {/* Un dispositivo que ya no esta dado de alta se conserva como opcion:
              perderlo al guardar borraria el objetivo sin decirlo. */}
          {!known && <option value={target.deviceId}>Dispositivo desconocido</option>}
          {options.map((device) => (
            <option key={device.id} value={device.id}>
              {device.name}
            </option>
          ))}
        </select>
      </div>

      <fieldset className={styles.field ?? ''}>
        <legend>Qué reproduce</legend>

        <ul className={styles.options ?? ''}>
          <li className={styles.option ?? ''}>
            <label>
              <input
                type="radio"
                name={sourceName}
                checked={target.source.kind === 'color'}
                onChange={() => {
                  onChange({ ...target, source: newTargetDraft(target.deviceId).source })
                }}
              />
              Un color fijo
            </label>
          </li>

          <li className={styles.option ?? ''}>
            <label>
              <input
                type="radio"
                name={sourceName}
                checked={target.source.kind === 'effect'}
                disabled={effects.length === 0}
                onChange={() => {
                  onChange({
                    ...target,
                    source: { kind: 'effect', effectId: effects[0]?.id ?? '' },
                  })
                }}
              />
              Un efecto guardado
            </label>
          </li>
        </ul>
      </fieldset>

      {target.source.kind === 'color' ? (
        <>
          <ColorPicker
            label="Color de la escena"
            color={target.source.color}
            disabled={false}
            // Las dos salidas del gesto acaban en el borrador: este selector no
            // manda nada al dispositivo.
            onPreview={(color) => {
              onChange({ ...target, source: { kind: 'color', color } })
            }}
            onCommit={(color) => {
              onChange({ ...target, source: { kind: 'color', color } })
            }}
          />
          <ControlNote id={noteId}>
            {`Una escena no guarda un color: guarda una referencia a un efecto. Al guardar se creará el efecto «${staticEffectName(target.source.color)}» en la biblioteca de efectos —o se reutilizará si ya está— y la escena lo referenciará.`}
          </ControlNote>
        </>
      ) : (
        <div className={styles.field ?? ''}>
          <label htmlFor={effectId}>Efecto</label>
          <select
            id={effectId}
            className={styles.input ?? ''}
            value={target.source.effectId}
            onChange={(event) => {
              onChange({ ...target, source: { kind: 'effect', effectId: event.target.value } })
            }}
          >
            {effects.map((effect) => (
              <option key={effect.id} value={effect.id}>
                {effect.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {removable && (
        <Button ariaLabel="Quitar este dispositivo de la escena" onClick={onRemove}>
          Quitar dispositivo
        </Button>
      )}
    </div>
  )
}
