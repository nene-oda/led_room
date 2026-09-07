/**
 * Perfiles en el dominio del cliente.
 *
 * Espejo de `Profile` del backend (backend/app/domain/profiles/models.py). Un
 * perfil es una **coleccion ordenada de escenas** con una marcada como
 * predeterminada, y activarlo es exactamente activar esa escena: hereda todos
 * sus errores porque es la misma operacion.
 *
 * Dos reglas del contrato que este modulo hace cumplir:
 *
 * 1. **La posicion de una escena es su indice en el array** al escribir, igual
 *    que los pasos de un efecto. Por eso `ProfileSceneDraft` no lleva
 *    `position`: guardarla ademas como campo permitiria representar un orden
 *    que contradijera al array.
 * 2. **El desempate de la escena predeterminada lo resuelve el servidor** y lo
 *    publica ya resuelto en `defaultSceneId`. Aqui NO se reimplementa: al abrir
 *    el editor se parte de lo que dijo el servidor, y al guardar se marca
 *    exactamente una, con lo que el desempate deja de tener nada que decidir.
 */

/** `profiles.name` es `VARCHAR(120)` con `min_length=1` en el contrato. */
export const NAME_MAX_LENGTH = 120

/** Una escena dentro de un perfil, tal y como se publica. */
export interface ProfileScene {
  readonly sceneId: string
  readonly position: number
  readonly isDefault: boolean
}

export interface Profile {
  readonly id: string
  readonly name: string
  readonly description: string | null
  /** Nombre de icono. El backend no lo interpreta y esta UI tampoco lo edita. */
  readonly icon: string | null
  /** Lo decide el servidor; no se envia al escribir. */
  readonly isBuiltin: boolean
  readonly scenes: readonly ProfileScene[]
  /**
   * Que escena activaria el perfil ahora mismo, **ya resuelta por el servidor**.
   * `null` = el perfil no tiene ninguna escena (activarlo daria 409).
   */
  readonly defaultSceneId: string | null
}

/** Una escena del borrador. Su posicion es su indice en el array. */
export interface ProfileSceneDraft {
  readonly sceneId: string
  readonly isDefault: boolean
}

export interface ProfileDraft {
  readonly name: string
  readonly description: string | null
  /** No se edita hoy; se conserva para no borrarlo al reemplazar. */
  readonly icon: string | null
  readonly scenes: readonly ProfileSceneDraft[]
}

export function newProfileDraft(): ProfileDraft {
  return { name: '', description: null, icon: null, scenes: [] }
}

/**
 * Abre un perfil guardado en el editor.
 *
 * La predeterminada se toma de `defaultSceneId`, que es la que **el servidor**
 * activaria, y no de las banderas `isDefault` crudas: si el perfil venia sin
 * ninguna marcada (o con varias), el editor enseñaria una cosa y el servidor
 * haria otra.
 */
export function draftFromProfile(profile: Profile): ProfileDraft {
  return {
    name: profile.name,
    description: profile.description,
    icon: profile.icon,
    scenes: profile.scenes.map((link) => ({
      sceneId: link.sceneId,
      isDefault: link.sceneId === profile.defaultSceneId,
    })),
  }
}

/** ¿Esta escena forma parte del perfil? */
export function includesScene(draft: ProfileDraft, sceneId: string): boolean {
  return draft.scenes.some((link) => link.sceneId === sceneId)
}

/**
 * Añade o quita una escena del perfil.
 *
 * Al añadir la primera queda marcada como predeterminada, y al quitar la
 * predeterminada la marca pasa a la primera que queda: asi el perfil nunca
 * llega al servidor sin una eleccion explicita, aunque el servidor sepa
 * desempatar.
 */
export function withScene(draft: ProfileDraft, sceneId: string, included: boolean): ProfileDraft {
  const scenes = included
    ? [...draft.scenes.filter((link) => link.sceneId !== sceneId), { sceneId, isDefault: false }]
    : draft.scenes.filter((link) => link.sceneId !== sceneId)

  return withResolvedDefault({ ...draft, scenes })
}

/** Marca la escena que activara el perfil. Exactamente una queda marcada. */
export function withDefaultScene(draft: ProfileDraft, sceneId: string): ProfileDraft {
  if (!includesScene(draft, sceneId)) return draft
  return {
    ...draft,
    scenes: draft.scenes.map((link) => ({ ...link, isDefault: link.sceneId === sceneId })),
  }
}

/** La escena marcada, o `null` si el perfil esta vacio. */
export function defaultSceneOf(draft: ProfileDraft): string | null {
  return draft.scenes.find((link) => link.isDefault)?.sceneId ?? null
}

/** Si nadie quedo marcado, marca la primera: la misma que elegiria el servidor. */
function withResolvedDefault(draft: ProfileDraft): ProfileDraft {
  const first = draft.scenes[0]
  if (first === undefined || draft.scenes.some((link) => link.isDefault)) return draft
  return withDefaultScene(draft, first.sceneId)
}

export type ProfileDraftField = 'name' | 'scenes'

export type ProfileDraftErrors = Readonly<Partial<Record<ProfileDraftField, string>>>

export function validateProfileDraft(draft: ProfileDraft): ProfileDraftErrors {
  const errors: { -readonly [K in ProfileDraftField]?: string } = {}

  const name = draft.name.trim()
  if (name.length === 0) {
    errors.name = 'El perfil necesita un nombre.'
  } else if (name.length > NAME_MAX_LENGTH) {
    errors.name = `El nombre no puede pasar de ${String(NAME_MAX_LENGTH)} caracteres.`
  }

  // El servidor acepta un perfil sin escenas, pero activarlo responderia 409:
  // se avisa aqui, que es donde tiene arreglo.
  if (draft.scenes.length === 0) {
    errors.scenes = 'Un perfil necesita al menos una escena: sin ella no se puede activar.'
  }

  return errors
}

export function hasProfileErrors(errors: ProfileDraftErrors): boolean {
  return Object.keys(errors).length > 0
}
