import { useId } from 'react'

import { ProfileEditor } from './ProfileEditor'
import { ProfileRow } from './ProfileRow'
import styles from '../ui/catalog.module.css'
import type { ProfileCatalog } from '../../hooks/useProfileCatalog'
import type { Scene } from '../../domain/scenes'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'
import { ModalCard } from '../ui/ModalCard'

export interface ProfileLibraryProps {
  readonly catalog: ProfileCatalog
  /** Catalogo de escenas: un perfil se compone eligiendo entre lo que existe. */
  readonly scenes: readonly Scene[]
  /** Escena que el servidor da por activa; un perfil se resalta por la suya. */
  readonly activeSceneId: string | null
  readonly activationReason: string | null
}

/**
 * La biblioteca de perfiles: listar, activar, crear, editar y borrar.
 *
 * En un dialogo como las demas bibliotecas. **No tiene barra rapida propia**:
 * un perfil no es mas que "activa esta escena", y las escenas ya estan a un
 * toque en la zona del pulgar; duplicar ese acceso solo daria dos botones que
 * hacen lo mismo.
 *
 * Este dialogo si es su propia region viva —incluidos los fallos de
 * activacion— porque un perfil solo se activa desde aqui.
 */
export function ProfileLibrary({
  catalog,
  scenes,
  activeSceneId,
  activationReason,
}: ProfileLibraryProps) {
  const reasonId = useId()
  const { state } = catalog

  return (
    <ModalCard
      title="Perfiles"
      summary={summarize(state.profiles.length)}
      actionText="Gestionar"
      actionLabel="Gestionar perfiles"
      dismissOnBackdrop={state.editing === null}
      onClose={catalog.cancelEdit}
    >
      <p className={styles.narration ?? ''} role="status" aria-live="polite">
        {state.message ?? narrate(state.status, state.profiles.length)}
      </p>

      {activationReason !== null && <ControlNote id={reasonId}>{activationReason}</ControlNote>}

      <ul className={styles.list ?? ''}>
        {state.profiles.map((profile) => (
          <ProfileRow
            key={profile.id}
            profile={profile}
            scenes={scenes}
            active={profile.defaultSceneId !== null && profile.defaultSceneId === activeSceneId}
            busy={state.pendingId === profile.id}
            activationBlockedBy={activationReason === null ? null : reasonId}
            onActivate={catalog.activate}
            onEdit={catalog.edit}
            onDelete={catalog.remove}
          />
        ))}
      </ul>

      <Button disabled={state.editing !== null} onClick={catalog.create}>
        Nuevo perfil
      </Button>

      {state.editing !== null && (
        <ProfileEditor
          key={state.editing.id ?? 'new'}
          initial={state.editing.draft}
          existing={state.editing.id !== null}
          saving={state.saving}
          scenes={scenes}
          onSave={catalog.save}
          onCancel={catalog.cancelEdit}
        />
      )}
    </ModalCard>
  )
}

function summarize(count: number): string {
  return count === 1 ? '1 guardado' : `${String(count)} guardados`
}

function narrate(status: 'loading' | 'ready' | 'failed', count: number): string {
  switch (status) {
    case 'loading':
      return 'Cargando los perfiles…'
    case 'failed':
      return 'No se pudo cargar el catálogo de perfiles.'
    case 'ready':
      return count === 0
        ? 'Todavía no hay ningún perfil guardado. Un perfil agrupa escenas y activa la que marques como predeterminada.'
        : `${String(count)} ${count === 1 ? 'perfil guardado' : 'perfiles guardados'}.`
  }
}
