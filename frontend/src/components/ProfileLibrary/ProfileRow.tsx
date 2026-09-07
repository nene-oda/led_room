import { useState } from 'react'

import styles from '../ui/catalog.module.css'
import type { Profile } from '../../domain/profiles'
import { sceneName, type Scene } from '../../domain/scenes'
import { Button } from '../ui/Button'

export interface ProfileRowProps {
  readonly profile: Profile
  /** Catalogo de escenas, para poder nombrar la que activaria el perfil. */
  readonly scenes: readonly Scene[]
  /**
   * La escena predeterminada de este perfil es la que el servidor da por activa.
   *
   * No existe un "perfil activo": activar un perfil es activar su escena, y esa
   * es la unica ranura que el servidor guarda. Inventar aqui otro estado seria
   * decir que el backend recuerda algo que no recuerda.
   */
  readonly active: boolean
  readonly busy: boolean
  readonly activationBlockedBy: string | null
  readonly onActivate: (profileId: string) => void
  readonly onEdit: (profileId: string) => void
  readonly onDelete: (profileId: string) => void
}

/**
 * Un perfil del catalogo.
 *
 * Enseña **que escena activaria**, porque es lo unico que hace: el
 * `default_scene_id` viene ya resuelto del servidor y aqui no se vuelve a
 * calcular el desempate.
 */
export function ProfileRow({
  profile,
  scenes,
  active,
  busy,
  activationBlockedBy,
  onActivate,
  onEdit,
  onDelete,
}: ProfileRowProps) {
  const [confirming, setConfirming] = useState(false)
  const target = profile.defaultSceneId === null ? null : sceneName(scenes, profile.defaultSceneId)

  return (
    <li className={`${styles.row ?? ''} ${active ? (styles.active ?? '') : ''}`}>
      <div className={styles.rowMain ?? ''}>
        <span className={styles.name ?? ''}>
          {profile.name}
          {profile.isBuiltin && <span className={styles.badge ?? ''}> · de fábrica</span>}
        </span>

        <span className={styles.meta ?? ''}>
          <span>{describe(profile.scenes.length, target, active)}</span>
          {profile.description !== null && <span>{profile.description}</span>}
        </span>
      </div>

      <div className={styles.actions ?? ''}>
        <Button
          busy={busy}
          // Un perfil sin escenas responderia 409: se dice antes de intentarlo.
          disabled={activationBlockedBy !== null || profile.defaultSceneId === null}
          describedBy={activationBlockedBy ?? undefined}
          ariaLabel={`Activar ${profile.name}`}
          onClick={() => {
            onActivate(profile.id)
          }}
        >
          Activar
        </Button>

        <Button
          busy={busy}
          ariaLabel={`Editar ${profile.name}`}
          onClick={() => {
            onEdit(profile.id)
          }}
        >
          Editar
        </Button>

        <Button
          busy={busy}
          ariaLabel={
            confirming ? `Confirmar el borrado de ${profile.name}` : `Borrar ${profile.name}`
          }
          onClick={() => {
            if (confirming) onDelete(profile.id)
            else setConfirming(true)
          }}
        >
          {confirming ? 'Confirmar' : 'Borrar'}
        </Button>
      </div>
    </li>
  )
}

function describe(count: number, target: string | null, active: boolean): string {
  if (count === 0) return 'Sin escenas: todavía no se puede activar'

  const scenes = count === 1 ? '1 escena' : `${String(count)} escenas`
  const activates = target === null ? 'activa su escena predeterminada' : `activa «${target}»`
  return active ? `${scenes} · ${activates}, que está puesta` : `${scenes} · ${activates}`
}
