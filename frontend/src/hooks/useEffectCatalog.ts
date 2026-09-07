import { useCallback, useEffect, useState } from 'react'

import { apiClient } from '../api/client'
import { draftFromEffect, newEffectDraft, type Effect, type EffectDraft } from '../domain/effects'
import { describeFailure } from '../state/failures'

/**
 * Lo que el editor esta editando. `id === null` es un efecto nuevo.
 *
 * Solo el punto de partida: la copia de trabajo vive en el propio editor, que
 * es quien cambia con cada tecla. Subirla aqui volveria a renderizar el panel
 * entero por cada pulsacion sin que nadie mas la necesite.
 */
export interface EffectEditing {
  readonly id: string | null
  readonly draft: EffectDraft
}

export interface EffectCatalogView {
  readonly status: 'loading' | 'ready' | 'failed'
  /** Catalogo, en el orden que da el servidor (por nombre). */
  readonly effects: readonly Effect[]
  /** Explicacion del ultimo fallo. Los textos normales los pone la vista. */
  readonly message: string | null
  /** Efecto sobre el que hay una operacion en curso (arrancar, parar, borrar). */
  readonly pendingId: string | null
  readonly saving: boolean
  readonly editing: EffectEditing | null
}

export interface EffectCatalog {
  readonly state: EffectCatalogView
  /**
   * Vuelve a pedir el catalogo.
   *
   * Existe porque los efectos se crean tambien desde fuera de este panel: una
   * escena de color fijo guarda su efecto `STATIC` antes de guardarse ella. Sin
   * esto, ese efecto no aparecería en la biblioteca hasta recargar la pagina, y
   * la escena diria que referencia algo que la lista no enseña.
   */
  readonly reload: () => void
  readonly start: (effectId: string) => void
  readonly stop: (effectId: string) => void
  readonly create: () => void
  readonly edit: (effectId: string) => void
  readonly cancelEdit: () => void
  readonly save: (draft: EffectDraft) => void
  readonly remove: (effectId: string) => void
}

const INITIAL: EffectCatalogView = {
  status: 'loading',
  effects: [],
  message: null,
  pendingId: null,
  saving: false,
  editing: null,
}

/**
 * El catalogo de efectos y las ordenes de reproduccion.
 *
 * **No guarda que efecto esta sonando.** Eso es estado global del servidor, lo
 * mantiene `LightStateProvider` y llega por `/ws`; duplicarlo aqui daria dos
 * indicadores que se contradicen en cuanto uno de los dos canales se retrasa.
 * Este hook solo sabe *que efectos existen* y *que operacion esta en curso*,
 * que es estado de una tarea y muere con el panel, igual que
 * `useDeviceDiscovery`.
 *
 * @param onApplied Se invoca tras una orden de reproduccion aceptada. El estado
 *   nuevo llega por el WebSocket, pero ese canal puede estar caido: rehidratar
 *   es lo que evita que el indicador se quede mintiendo mientras el socket
 *   reconecta. Dependencia explicita; el hook no conoce el estado global.
 */
export function useEffectCatalog({ onApplied }: { readonly onApplied: () => void }): EffectCatalog {
  const [state, setState] = useState<EffectCatalogView>(INITIAL)
  const editing = state.editing

  const load = useCallback(async (): Promise<void> => {
    try {
      const effects = await apiClient.listEffects()
      setState((current) => ({ ...current, status: 'ready', effects, message: null }))
    } catch (error) {
      setState((current) => ({
        ...current,
        // Un fallo al recargar no borra el catalogo que ya se veia: una lista
        // vacia con un aviso miente menos que una lista vacia sin el.
        status: current.status === 'ready' ? 'ready' : 'failed',
        message: describeFailure(error, 'effect').message,
      }))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const fail = useCallback((error: unknown) => {
    setState((current) => ({
      ...current,
      pendingId: null,
      saving: false,
      message: describeFailure(error, 'effect').message,
    }))
  }, [])

  /**
   * Una orden sobre un efecto concreto: marca "en curso", ejecuta y remata.
   *
   * El remate se pasa como funcion en vez de como bandera porque las dos
   * operaciones terminan de forma distinta —reproducir rehidrata el estado
   * global, borrar recarga el catalogo— y un booleano solo esconderia ese
   * `if` dentro de esta funcion.
   */
  const run = useCallback(
    (effectId: string, operation: () => Promise<unknown>, done: () => void | Promise<void>) => {
      setState((current) => ({ ...current, pendingId: effectId, message: null }))

      void (async () => {
        try {
          await operation()
          setState((current) => ({ ...current, pendingId: null }))
          await done()
        } catch (error) {
          fail(error)
        }
      })()
    },
    [fail],
  )

  const start = useCallback(
    (effectId: string) => {
      run(effectId, () => apiClient.startEffect(effectId), onApplied)
    },
    [onApplied, run],
  )

  const stop = useCallback(
    (effectId: string) => {
      run(effectId, () => apiClient.stopEffect(effectId), onApplied)
    },
    [onApplied, run],
  )

  const remove = useCallback(
    (effectId: string) => {
      run(effectId, () => apiClient.deleteEffect(effectId), load)
      // Editar algo que ya no existe solo puede acabar en un 404 al guardar.
      setState((current) =>
        current.editing?.id === effectId ? { ...current, editing: null } : current,
      )
    },
    [load, run],
  )

  const create = useCallback(() => {
    setState((current) => ({
      ...current,
      editing: { id: null, draft: newEffectDraft() },
      message: null,
    }))
  }, [])

  /**
   * Abre el editor con la copia **autoritativa** del servidor.
   *
   * Se relee aunque el efecto ya este en la lista: el catalogo no viaja por el
   * WebSocket, asi que la copia local puede ser vieja, y `PUT` es un reemplazo
   * completo. Editar sobre lo rancio borraria en silencio lo que otro cliente
   * acabara de guardar.
   */
  const edit = useCallback(
    (effectId: string) => {
      setState((current) => ({ ...current, pendingId: effectId, message: null }))

      void (async () => {
        try {
          const effect = await apiClient.getEffect(effectId)
          setState((current) => ({
            ...current,
            pendingId: null,
            editing: { id: effect.id, draft: draftFromEffect(effect) },
          }))
        } catch (error) {
          fail(error)
        }
      })()
    },
    [fail],
  )

  const cancelEdit = useCallback(() => {
    setState((current) => ({ ...current, editing: null }))
  }, [])

  const save = useCallback(
    (draft: EffectDraft) => {
      if (editing === null) return
      const { id } = editing

      setState((current) => ({ ...current, saving: true, message: null }))

      void (async () => {
        try {
          // Crear o reemplazar, segun haya identidad. El `id` de un efecto nuevo
          // lo genera el SERVIDOR: el cuerpo de `POST /effects` no lo lleva.
          await (id === null ? apiClient.createEffect(draft) : apiClient.replaceEffect(id, draft))
          setState((current) => ({ ...current, saving: false, editing: null }))
          // Se recarga en vez de insertar la respuesta: el orden del catalogo es
          // del servidor (por nombre) y colarlo aqui lo dejaria descolocado.
          await load()
        } catch (error) {
          fail(error)
        }
      })()
    },
    [editing, fail, load],
  )

  const reload = useCallback(() => {
    void load()
  }, [load])

  return { state, reload, start, stop, create, edit, cancelEdit, save, remove }
}
