import { useState } from 'react'

import styles from '../ui/catalog.module.css'
import type { Effect } from '../../domain/effects'
import { describeTargets, type Scene } from '../../domain/scenes'
import { Button } from '../ui/Button'

export interface SceneRowProps {
  readonly scene: Scene
  /** Catalogo de efectos, para poder decir QUE reproduce la escena. */
  readonly effects: readonly Effect[]
  /** La da por activa el servidor. Nunca se deduce de haber pulsado el boton. */
  readonly active: boolean
  readonly busy: boolean
  /** Id del texto que explica por que no se puede activar; `null` = se puede. */
  readonly activationBlockedBy: string | null
  readonly onActivate: (sceneId: string) => void
  readonly onEdit: (sceneId: string) => void
  readonly onDuplicate: (sceneId: string) => void
  readonly onDelete: (sceneId: string) => void
  readonly onToggleFavorite: (sceneId: string) => void
}

/**
 * Una escena del catalogo.
 *
 * Activar es la accion principal y va primero; favorita, duplicar, editar y
 * borrar despues, porque activar es lo que se hace a diario.
 *
 * **Borrar pide confirmacion en el propio boton** en vez de abrir un dialogo,
 * igual que en la biblioteca de efectos: es irreversible y con el pulgar se
 * pulsa sin querer, pero un modal obligaria a reimplementar trampa de foco y
 * Escape para una lista.
 *
 * No lleva region viva: lo que esta activo lo anuncia `SceneQuickBar`, que es la
 * unica, para que activar una escena no produzca dos anuncios.
 */
export function SceneRow({
  scene,
  effects,
  active,
  busy,
  activationBlockedBy,
  onActivate,
  onEdit,
  onDuplicate,
  onDelete,
  onToggleFavorite,
}: SceneRowProps) {
  const [confirming, setConfirming] = useState(false)

  return (
    <li className={`${styles.row ?? ''} ${active ? (styles.active ?? '') : ''}`}>
      <div className={styles.rowMain ?? ''}>
        <span className={styles.name ?? ''}>
          {scene.name}
          {active && <span className={styles.badge ?? ''}> · activa</span>}
          {scene.isBuiltin && <span className={styles.badge ?? ''}> · de fábrica</span>}
        </span>

        <span className={styles.meta ?? ''}>
          <span>{describeTargets(scene, effects)}</span>
          {scene.description !== null && <span>{scene.description}</span>}
        </span>
      </div>

      <div className={styles.actions ?? ''}>
        <Button
          busy={busy}
          disabled={activationBlockedBy !== null}
          describedBy={activationBlockedBy ?? undefined}
          current={active}
          ariaLabel={active ? `${scene.name}, activa` : `Activar ${scene.name}`}
          onClick={() => {
            onActivate(scene.id)
          }}
        >
          {active ? 'Activa' : 'Activar'}
        </Button>

        {/* Favorita SI es un estado de dos posiciones y se puede desmarcar: por
            eso aqui `pressed` y no `current`. */}
        <Button
          busy={busy}
          pressed={scene.isFavorite}
          ariaLabel={
            scene.isFavorite
              ? `Quitar ${scene.name} de las escenas rápidas`
              : `Añadir ${scene.name} a las escenas rápidas`
          }
          onClick={() => {
            onToggleFavorite(scene.id)
          }}
        >
          Favorita
        </Button>

        <Button
          busy={busy}
          ariaLabel={`Editar ${scene.name}`}
          onClick={() => {
            onEdit(scene.id)
          }}
        >
          Editar
        </Button>

        <Button
          busy={busy}
          ariaLabel={`Duplicar ${scene.name}`}
          onClick={() => {
            onDuplicate(scene.id)
          }}
        >
          Duplicar
        </Button>

        <Button
          busy={busy}
          ariaLabel={confirming ? `Confirmar el borrado de ${scene.name}` : `Borrar ${scene.name}`}
          onClick={() => {
            if (confirming) onDelete(scene.id)
            else setConfirming(true)
          }}
        >
          {confirming ? 'Confirmar' : 'Borrar'}
        </Button>
      </div>
    </li>
  )
}
