import { useCallback, useEffect, useState } from 'react'

import { apiClient } from '../api/client'
import { draftFromProfile, newProfileDraft, type Profile, type ProfileDraft } from '../domain/profiles'
import { describeFailure } from '../state/failures'

/** Lo que el editor esta editando. `id === null` es un perfil nuevo. */
export interface ProfileEditing {
  readonly id: string | null
  readonly draft: ProfileDraft
}

export interface ProfileCatalogView {
  readonly status: 'loading' | 'ready' | 'failed'
  readonly profiles: readonly Profile[]
  /**
   * Explicacion del ultimo fallo, de catalogo o de activacion.
   *
   * Aqui **no** se separan como en las escenas: un perfil solo se activa desde
   * su propia lista, asi que el aviso se lee siempre en el mismo sitio y dos
   * campos solo añadirian una rama que nadie distingue.
   */
  readonly message: string | null
  readonly pendingId: string | null
  readonly saving: boolean
  readonly editing: ProfileEditing | null
}

export interface ProfileCatalog {
  readonly state: ProfileCatalogView
  readonly activate: (profileId: string) => void
  readonly create: () => void
  readonly edit: (profileId: string) => void
  readonly cancelEdit: () => void
  readonly save: (draft: ProfileDraft) => void
  readonly remove: (profileId: string) => void
}

const INITIAL: ProfileCatalogView = {
  status: 'loading',
  profiles: [],
  message: null,
  pendingId: null,
  saving: false,
  editing: null,
}

/**
 * El catalogo de perfiles y la orden de activarlos.
 *
 * **Activar un perfil es activar su escena predeterminada**, asi que la escena
 * que quede puesta la enseña el indicador de escenas, no este hook: la ranura
 * `scene` del estado global es la misma en los dos casos y tener aqui un
 * "perfil activo" propio seria inventar un estado que el servidor no guarda.
 *
 * @param onActivated Igual que en escenas y efectos: rehidrata el estado global
 *   tras una activacion aceptada, por si el WebSocket esta reconectando.
 */
export function useProfileCatalog({
  onActivated,
}: {
  readonly onActivated: () => void
}): ProfileCatalog {
  const [state, setState] = useState<ProfileCatalogView>(INITIAL)
  const editing = state.editing

  const load = useCallback(async (): Promise<void> => {
    try {
      const profiles = await apiClient.listProfiles()
      setState((current) => ({ ...current, status: 'ready', profiles, message: null }))
    } catch (error) {
      setState((current) => ({
        ...current,
        status: current.status === 'ready' ? 'ready' : 'failed',
        message: describeFailure(error, 'profile').message,
      }))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const fail = useCallback((error: unknown, context: 'profile' | 'profile-activation') => {
    setState((current) => ({
      ...current,
      pendingId: null,
      saving: false,
      message: describeFailure(error, context).message,
    }))
  }, [])

  const run = useCallback(
    (profileId: string, operation: () => Promise<unknown>, done: () => void | Promise<void>) => {
      setState((current) => ({ ...current, pendingId: profileId, message: null }))

      void (async () => {
        try {
          await operation()
          setState((current) => ({ ...current, pendingId: null }))
          await done()
        } catch (error) {
          fail(error, 'profile')
        }
      })()
    },
    [fail],
  )

  /**
   * Activa el perfil. Hereda TODOS los errores de activar una escena porque es
   * la misma operacion; el contexto del mensaje lo dice asi.
   */
  const activate = useCallback(
    (profileId: string) => {
      setState((current) => ({ ...current, pendingId: profileId, message: null }))

      void (async () => {
        try {
          await apiClient.activateProfile(profileId)
          setState((current) => ({ ...current, pendingId: null }))
          onActivated()
        } catch (error) {
          fail(error, 'profile-activation')
        }
      })()
    },
    [fail, onActivated],
  )

  const create = useCallback(() => {
    setState((current) => ({ ...current, editing: { id: null, draft: newProfileDraft() }, message: null }))
  }, [])

  /** Se relee del servidor por el mismo motivo que las escenas: `PUT` reemplaza. */
  const edit = useCallback(
    (profileId: string) => {
      setState((current) => ({ ...current, pendingId: profileId, message: null }))

      void (async () => {
        try {
          const profile = await apiClient.getProfile(profileId)
          setState((current) => ({
            ...current,
            pendingId: null,
            editing: { id: profile.id, draft: draftFromProfile(profile) },
          }))
        } catch (error) {
          fail(error, 'profile')
        }
      })()
    },
    [fail],
  )

  const cancelEdit = useCallback(() => {
    setState((current) => ({ ...current, editing: null }))
  }, [])

  const save = useCallback(
    (draft: ProfileDraft) => {
      if (editing === null) return
      const { id } = editing

      setState((current) => ({ ...current, saving: true, message: null }))

      void (async () => {
        try {
          await (id === null
            ? apiClient.createProfile(draft)
            : apiClient.replaceProfile(id, draft))
          setState((current) => ({ ...current, saving: false, editing: null }))
          await load()
        } catch (error) {
          fail(error, 'profile')
        }
      })()
    },
    [editing, fail, load],
  )

  const remove = useCallback(
    (profileId: string) => {
      // Borra el perfil y sus enlaces; las escenas se conservan, son catalogo.
      run(profileId, () => apiClient.deleteProfile(profileId), load)
      setState((current) =>
        current.editing?.id === profileId ? { ...current, editing: null } : current,
      )
    },
    [load, run],
  )

  return { state, activate, create, edit, cancelEdit, save, remove }
}
