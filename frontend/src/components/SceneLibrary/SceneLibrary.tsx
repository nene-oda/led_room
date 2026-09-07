import { useId } from 'react'

import { SceneEditor } from './SceneEditor'
import { SceneRow } from './SceneRow'
import styles from '../ui/catalog.module.css'
import type { Effect } from '../../domain/effects'
import type { SceneCatalog } from '../../hooks/useSceneCatalog'
import type { RegisteredDevice } from '../../state/lightStateContext'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'
import { ModalCard } from '../ui/ModalCard'

export interface SceneLibraryProps {
  readonly catalog: SceneCatalog
  /** Catalogo de efectos: una escena los referencia, no los lleva dentro. */
  readonly effects: readonly Effect[]
  /** Dispositivos dados de alta, para elegir a cual apunta cada objetivo. */
  readonly devices: readonly RegisteredDevice[]
  /** Escena que el servidor da por activa. */
  readonly activeSceneId: string | null
  /** Por que no se puede activar nada ahora mismo. `null` = se puede. */
  readonly activationReason: string | null
}

/**
 * La biblioteca de escenas: listar, activar, crear, editar, duplicar, borrar y
 * marcar como rapida.
 *
 * En un dialogo, como las demas bibliotecas: **activar es lo que se hace a
 * diario y eso vive fuera**, en `SceneQuickBar`. Aqui esta la lista completa
 * porque tambien se activa lo que no es favorito, pero editar es la tarea
 * principal de este dialogo y es la que se hace una vez.
 *
 * Su narracion cuenta el **catalogo** (cargar, guardar, borrar) y tambien los
 * fallos de **activar**, aunque el titular de esos sea la barra de escenas
 * rapidas: mientras el dialogo esta abierto, la barra queda tapada y fuera de
 * `aria-modal`, asi que no se ve ni se anuncia. Ver `news`.
 */
export function SceneLibrary({
  catalog,
  effects,
  devices,
  activeSceneId,
  activationReason,
}: SceneLibraryProps) {
  const reasonId = useId()
  const { state } = catalog

  return (
    <ModalCard
      title="Escenas"
      summary={summarize(state.scenes.length)}
      actionText="Gestionar"
      actionLabel="Gestionar escenas"
      dismissOnBackdrop={state.editing === null}
      onClose={catalog.cancelEdit}
    >
      {/* Una sola region viva, con las dos ultimas noticias: la del catalogo
          (cargar, guardar, borrar) y la de activar. Dos regiones obligarian a
          dejar una vacia, y una region que aparece despues no se anuncia de
          forma fiable. */}
      <p className={styles.narration ?? ''} role="status" aria-live="polite">
        {news(state)}
      </p>

      {activationReason !== null && <ControlNote id={reasonId}>{activationReason}</ControlNote>}

      <ul className={styles.list ?? ''}>
        {state.scenes.map((scene) => (
          <SceneRow
            key={scene.id}
            scene={scene}
            effects={effects}
            active={scene.id === activeSceneId}
            busy={state.pendingId === scene.id}
            activationBlockedBy={activationReason === null ? null : reasonId}
            onActivate={catalog.activate}
            onEdit={catalog.edit}
            onDuplicate={catalog.duplicate}
            onDelete={catalog.remove}
            onToggleFavorite={catalog.toggleFavorite}
          />
        ))}
      </ul>

      <Button disabled={state.editing !== null} onClick={catalog.create}>
        Nueva escena
      </Button>

      {state.editing !== null && (
        // `key` reinicia el formulario al cambiar de escena: sin el, abrir otra
        // reutilizaria el borrador de la anterior.
        <SceneEditor
          key={state.editing.id ?? 'new'}
          initial={state.editing.draft}
          existing={state.editing.id !== null}
          saving={state.saving}
          devices={devices}
          effects={effects}
          onSave={catalog.save}
          onCancel={catalog.cancelEdit}
        />
      )}
    </ModalCard>
  )
}

function summarize(count: number): string {
  return count === 1 ? '1 guardada' : `${String(count)} guardadas`
}

/**
 * Que se cuenta en el dialogo: lo ultimo que fallo, y si no, el estado.
 *
 * El fallo de **activar** tambien se cuenta aqui, aunque su titular sea la
 * barra de escenas rapidas: con el dialogo abierto, la barra queda tapada y
 * fuera de `aria-modal`, asi que nadie la veria ni la oiria. No suena dos veces
 * por lo mismo porque solo una de las dos es alcanzable en cada momento.
 */
function news(state: SceneCatalog['state']): string {
  const failures = [state.message, state.activationMessage].filter((text) => text !== null)
  return failures.length === 0 ? narrate(state.status, state.scenes.length) : failures.join(' ')
}

function narrate(status: 'loading' | 'ready' | 'failed', count: number): string {
  switch (status) {
    case 'loading':
      return 'Cargando el catálogo de escenas…'
    case 'failed':
      // Con este estado siempre hay `message`; esto solo cierra el tipo.
      return 'No se pudo cargar el catálogo de escenas.'
    case 'ready':
      return count === 0
        ? 'Todavía no hay ninguna escena guardada. Crea una para empezar.'
        : `${String(count)} ${count === 1 ? 'escena guardada' : 'escenas guardadas'}.`
  }
}
