import { useCallback, useEffect, useState } from 'react'

import { apiClient } from '../api/client'
import type { Effect } from '../domain/effects'
import {
  draftFromScene,
  findStaticEffect,
  newSceneDraft,
  sceneWriteFrom,
  staticEffectDraft,
  staticEffectName,
  type Scene,
  type SceneDraft,
  type SceneTarget,
} from '../domain/scenes'
import { describeFailure } from '../state/failures'

/** Lo que el editor esta editando. `id === null` es una escena nueva. */
export interface SceneEditing {
  readonly id: string | null
  readonly draft: SceneDraft
}

export interface SceneCatalogView {
  readonly status: 'loading' | 'ready' | 'failed'
  /** Catalogo, en el orden que da el servidor (por nombre). */
  readonly scenes: readonly Scene[]
  /**
   * Explicacion del ultimo fallo del **catalogo** (cargar, guardar, borrar).
   *
   * Separado de `activationMessage` porque se leen en sitios distintos: esto
   * pasa dentro del panel, donde el usuario acaba de tocar el formulario.
   */
  readonly message: string | null
  /**
   * Explicacion del ultimo fallo al **activar**.
   *
   * Vive aparte porque activar se hace desde fuera del panel (las escenas
   * favoritas estan a un toque) y su aviso tiene que aparecer alli. Juntarlos
   * obligaria a repetir el mismo texto en dos regiones vivas, y un lector de
   * pantalla lo anunciaria dos veces.
   */
  readonly activationMessage: string | null
  /** Escena sobre la que hay una operacion en curso. */
  readonly pendingId: string | null
  readonly saving: boolean
  readonly editing: SceneEditing | null
}

export interface SceneCatalog {
  readonly state: SceneCatalogView
  readonly activate: (sceneId: string) => void
  readonly create: () => void
  readonly edit: (sceneId: string) => void
  readonly cancelEdit: () => void
  readonly save: (draft: SceneDraft) => void
  readonly duplicate: (sceneId: string) => void
  readonly remove: (sceneId: string) => void
  readonly toggleFavorite: (sceneId: string) => void
}

const INITIAL: SceneCatalogView = {
  status: 'loading',
  scenes: [],
  message: null,
  activationMessage: null,
  pendingId: null,
  saving: false,
  editing: null,
}

export interface SceneCatalogOptions {
  /** Dispositivo al que apunta una escena nueva. `null` = no hay ninguno. */
  readonly defaultDeviceId: string | null
  /** Catalogo de efectos. Se necesita para reutilizar el efecto de un color. */
  readonly effects: readonly Effect[]
  /**
   * Se invoca cuando esta pantalla **crea** un efecto (el `STATIC` de un color
   * fijo). El catalogo de efectos lo mantiene otro hook: avisarle es lo que
   * evita dos copias de la misma lista.
   */
  readonly onEffectsChanged: () => void
  /**
   * Se invoca tras una activacion aceptada. El estado nuevo llega por el
   * WebSocket, pero ese canal puede estar caido: rehidratar es lo que evita que
   * el indicador se quede mintiendo mientras el socket reconecta.
   */
  readonly onActivated: () => void
}

/**
 * El catalogo de escenas y la orden de activarlas.
 *
 * **No guarda cual esta activa.** Eso es estado global del servidor, lo mantiene
 * `LightStateProvider` y llega por `/ws`; duplicarlo aqui daria dos indicadores
 * que se contradicen en cuanto uno de los dos canales se retrasa. Este hook solo
 * sabe *que escenas existen* y *que operacion esta en curso*, igual que
 * `useEffectCatalog` con los efectos.
 *
 * Aqui vive **la unica pieza de la aplicacion que sabe que una escena de color
 * fijo son dos escrituras**: primero el efecto `STATIC`, despues la escena que
 * lo referencia. Es una regla del contrato del backend, no una comodidad de la
 * UI, y por eso esta en un solo sitio.
 */
export function useSceneCatalog({
  defaultDeviceId,
  effects,
  onEffectsChanged,
  onActivated,
}: SceneCatalogOptions): SceneCatalog {
  const [state, setState] = useState<SceneCatalogView>(INITIAL)
  const editing = state.editing

  const load = useCallback(async (): Promise<void> => {
    try {
      const scenes = await apiClient.listScenes()
      setState((current) => ({ ...current, status: 'ready', scenes, message: null }))
    } catch (error) {
      setState((current) => ({
        ...current,
        // Un fallo al recargar no borra el catalogo que ya se veia.
        status: current.status === 'ready' ? 'ready' : 'failed',
        message: describeFailure(error, 'scene').message,
      }))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const fail = useCallback((error: unknown, extra?: string) => {
    const { message } = describeFailure(error, 'scene')
    setState((current) => ({
      ...current,
      pendingId: null,
      saving: false,
      message: extra === undefined ? message : `${message} ${extra}`,
    }))
  }, [])

  /** Una orden sobre una escena concreta: marca "en curso", ejecuta y remata. */
  const run = useCallback(
    (sceneId: string, operation: () => Promise<unknown>, done: () => void | Promise<void>) => {
      setState((current) => ({ ...current, pendingId: sceneId, message: null }))

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

  /**
   * Activar es atomico en el servidor: o suena la escena entera o no suena
   * nada. Por eso el fallo no se cuenta como "se activó a medias" y por eso no
   * hay ningun indicador optimista: el resaltado sale del estado global cuando
   * llega `scene.activated`.
   */
  const activate = useCallback(
    (sceneId: string) => {
      setState((current) => ({ ...current, pendingId: sceneId, activationMessage: null }))

      void (async () => {
        try {
          await apiClient.activateScene(sceneId)
          setState((current) => ({ ...current, pendingId: null }))
          onActivated()
        } catch (error) {
          setState((current) => ({
            ...current,
            pendingId: null,
            activationMessage: describeFailure(error, 'scene-activation').message,
          }))
        }
      })()
    },
    [onActivated],
  )

  const create = useCallback(() => {
    setState((current) => ({
      ...current,
      editing: { id: null, draft: newSceneDraft(defaultDeviceId) },
      message: null,
    }))
  }, [defaultDeviceId])

  /**
   * Abre el editor con la copia **autoritativa** del servidor.
   *
   * Se relee aunque la escena ya este en la lista: el catalogo no viaja por el
   * WebSocket y `PUT` es un reemplazo completo, asi que editar sobre lo rancio
   * borraria en silencio lo que otro cliente acabara de guardar.
   */
  const edit = useCallback(
    (sceneId: string) => {
      setState((current) => ({ ...current, pendingId: sceneId, message: null }))

      void (async () => {
        try {
          const scene = await apiClient.getScene(sceneId)
          setState((current) => ({
            ...current,
            pendingId: null,
            editing: { id: scene.id, draft: draftFromScene(scene, effects) },
          }))
        } catch (error) {
          fail(error)
        }
      })()
    },
    [effects, fail],
  )

  const cancelEdit = useCallback(() => {
    setState((current) => ({ ...current, editing: null }))
  }, [])

  const save = useCallback(
    (draft: SceneDraft) => {
      if (editing === null) return
      const { id } = editing

      setState((current) => ({ ...current, saving: true, message: null }))

      void (async () => {
        // Lo que se creo antes de que fallara la escena, para poder decirlo: un
        // efecto guardado que nadie referencia no puede desaparecer en silencio
        // de la explicacion, porque no desaparece de la biblioteca.
        const created: string[] = []
        try {
          const targets: SceneTarget[] = []
          for (const target of draft.targets) {
            let effectId: string
            if (target.source.kind === 'effect') {
              effectId = target.source.effectId
            } else {
              // Reutiliza el efecto que ya se genero para ese color exacto en
              // vez de dejar copias identicas en la biblioteca.
              const existing = findStaticEffect(effects, target.source.color)
              if (existing === undefined) {
                const { color } = target.source
                const effect = await apiClient.createEffect(staticEffectDraft(color))
                created.push(staticEffectName(color))
                effectId = effect.id
              } else {
                effectId = existing.id
              }
            }

            targets.push({
              deviceId: target.deviceId,
              effectId,
              brightness: target.brightness,
              speed: target.speed,
              enabled: target.enabled,
            })
          }

          const scene = {
            name: draft.name,
            description: draft.description,
            icon: draft.icon,
            isFavorite: draft.isFavorite,
            targets,
          }

          // Crear o reemplazar, segun haya identidad. El `id` de una escena
          // nueva lo genera el SERVIDOR: el cuerpo de `POST /scenes` no lo lleva.
          await (id === null ? apiClient.createScene(scene) : apiClient.replaceScene(id, scene))
          setState((current) => ({ ...current, saving: false, editing: null }))
          if (created.length > 0) onEffectsChanged()
          // Se recarga en vez de insertar la respuesta: el orden del catalogo
          // es del servidor (por nombre) y colarlo aqui lo dejaria descolocado.
          await load()
        } catch (error) {
          if (created.length > 0) onEffectsChanged()
          fail(
            error,
            created.length === 0
              ? undefined
              : `El efecto «${created.join('», «')}» sí quedó guardado en la biblioteca de efectos.`,
          )
        }
      })()
    },
    [editing, effects, fail, load, onEffectsChanged],
  )

  const duplicate = useCallback(
    (sceneId: string) => {
      // Sin nombre: lo pone el servidor con su sufijo de copia. Inventarlo aqui
      // seria una segunda definicion de la misma regla.
      run(sceneId, () => apiClient.duplicateScene(sceneId), load)
    },
    [load, run],
  )

  const remove = useCallback(
    (sceneId: string) => {
      run(sceneId, () => apiClient.deleteScene(sceneId), load)
      // Editar algo que ya no existe solo puede acabar en un 404 al guardar.
      setState((current) =>
        current.editing?.id === sceneId ? { ...current, editing: null } : current,
      )
    },
    [load, run],
  )

  /**
   * Marca o desmarca como favorita.
   *
   * `PUT` es un reemplazo completo, asi que cambiar una bandera obliga a
   * reenviar la escena entera. Se relee del servidor primero: hacerlo desde la
   * copia de la lista pisaria lo que otro cliente acabara de cambiar.
   */
  const toggleFavorite = useCallback(
    (sceneId: string) => {
      run(
        sceneId,
        async () => {
          const scene = await apiClient.getScene(sceneId)
          const write = sceneWriteFrom(scene)
          await apiClient.replaceScene(sceneId, { ...write, isFavorite: !scene.isFavorite })
        },
        load,
      )
    },
    [load, run],
  )

  return { state, activate, create, edit, cancelEdit, save, duplicate, remove, toggleFavorite }
}
