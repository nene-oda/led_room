/**
 * Escenas en el dominio del cliente.
 *
 * Espejo de `Scene` del backend (backend/app/domain/scenes/models.py) con las
 * mismas dos diferencias de siempre: camelCase y `RGBColor` en vez de
 * `#RRGGBB`. La traduccion vive en `api/dto.ts`.
 *
 * Lo que este modulo existe para dejar claro:
 *
 * 1. **Una escena NO lleva el efecto dentro: lo referencia.** Un objetivo exige
 *    un `deviceId` y un `effectId` que ya existan. El README 13 dibujaba el
 *    efecto incrustado; el esquema congelado dice otra cosa
 *    (backend/app/api/schemas/scenes.py) y manda el esquema.
 * 2. **Por eso "una escena de color fijo" son DOS escrituras**: primero un
 *    efecto `STATIC` de un paso y despues la escena que lo referencia. La UI
 *    ofrece el atajo, pero no lo esconde: `staticEffectName` da el nombre con
 *    el que ese efecto aparecera en la biblioteca, y la pantalla lo dice antes
 *    de guardar.
 * 3. **`brightness` y `speed` de un objetivo son anulaciones por objetivo**,
 *    no campos de la escena: `null` significa "usa lo del efecto", nunca cero.
 *    El editor no las ofrece pero **las conserva**, porque `PUT /scenes/{id}`
 *    es un reemplazo completo y perderlas destruiria en silencio algo que el
 *    usuario no ha tocado.
 */
import { toHex, type RGBColor } from './color'
import {
  newEffectDraft,
  withEffectType,
  withStepColor,
  type Effect,
  type EffectDraft,
} from './effects'

/** `scenes.name` es `VARCHAR(120)` con `min_length=1` en el contrato. */
export const NAME_MAX_LENGTH = 120

/**
 * Que efecto aplica una escena sobre un dispositivo.
 *
 * No tiene identidad propia: la clave real es `(escena, dispositivo)`, la misma
 * UNIQUE que declara la tabla. Por eso dos objetivos al mismo dispositivo son
 * un 422 y el editor no los deja construir.
 */
export interface SceneTarget {
  readonly deviceId: string
  readonly effectId: string
  /** `null` = usa el brillo del efecto. No es lo mismo que 0. */
  readonly brightness: number | null
  /** `null` = usa la velocidad del efecto. Multiplicador, no una duracion. */
  readonly speed: number | null
  /** Un objetivo deshabilitado se guarda pero no se reproduce. */
  readonly enabled: boolean
}

/** Una escena guardada, tal y como la publica `GET /scenes`. */
export interface Scene {
  readonly id: string
  readonly name: string
  readonly description: string | null
  /** Nombre de icono. El backend no lo interpreta y esta UI tampoco lo edita. */
  readonly icon: string | null
  /** Lo decide el servidor; no se envia al escribir. */
  readonly isBuiltin: boolean
  readonly isFavorite: boolean
  readonly targets: readonly SceneTarget[]
}

/**
 * Una escena lista para escribir: **sin identidad y con todos los efectos ya
 * resueltos**.
 *
 * Separado de `SceneDraft` a proposito: el borrador puede pedir "un color
 * fijo", que todavia no es ningun efecto guardado. Esto es lo que se manda, y
 * por tanto todos sus objetivos referencian un `effectId` que ya existe.
 */
export interface SceneWrite {
  readonly name: string
  readonly description: string | null
  readonly icon: string | null
  readonly isFavorite: boolean
  readonly targets: readonly SceneTarget[]
}

/**
 * De donde saca su luz un objetivo, tal y como lo elige el usuario.
 *
 * `color` no es un tercer tipo de escena: es la promesa de crear (o reutilizar)
 * un efecto `STATIC` de un paso al guardar. Modelarlo asi es lo que permite que
 * la pantalla ofrezca el atajo y a la vez cuente lo que va a hacer.
 */
export type SceneSource =
  | { readonly kind: 'effect'; readonly effectId: string }
  | { readonly kind: 'color'; readonly color: RGBColor }

export interface SceneTargetDraft {
  readonly deviceId: string
  readonly source: SceneSource
  /** No se edita hoy; se conserva para no borrarlo al reemplazar. */
  readonly enabled: boolean
  /** No se edita hoy; se conserva por el mismo motivo. */
  readonly brightness: number | null
  /** No se edita hoy; se conserva por el mismo motivo. */
  readonly speed: number | null
}

/** Lo que el editor manipula: una escena **sin identidad**. */
export interface SceneDraft {
  readonly name: string
  readonly description: string | null
  /** No se edita hoy; se conserva para no borrarlo al reemplazar. */
  readonly icon: string | null
  readonly isFavorite: boolean
  readonly targets: readonly SceneTargetDraft[]
}

/** Color inicial de una escena nueva: ambar cálido, distinto del blanco. */
const DEFAULT_SCENE_COLOR: RGBColor = { r: 255, g: 147, b: 41 }

/**
 * Nombre del efecto que respalda un color fijo.
 *
 * Es **determinista a proposito**: es lo que permite reutilizar el efecto que
 * ya se creo para ese mismo color en vez de llenar la biblioteca de copias, y
 * lo que permite reconocerlo al volver a abrir la escena. Se enseña en la
 * pantalla antes de guardar: el usuario tiene que saber que ese efecto va a
 * aparecer en su biblioteca.
 */
export function staticEffectName(color: RGBColor): string {
  return `Color fijo ${toHex(color)}`
}

const STATIC_DESCRIPTION = 'Efecto de un solo color creado desde una escena.'

/**
 * Borrador del efecto `STATIC` que respalda un color fijo.
 *
 * Se construye componiendo el dominio de efectos en vez de escribir el objeto a
 * mano: asi los valores por defecto (fps, brillo, bucle) y las cotas del tipo
 * salen de un solo sitio, que es `domain/effects.ts`.
 */
export function staticEffectDraft(color: RGBColor): EffectDraft {
  const base = withStepColor(withEffectType(newEffectDraft(), 'STATIC'), 0, color)
  return { ...base, name: staticEffectName(color), description: STATIC_DESCRIPTION }
}

/**
 * ¿Es este efecto uno de los que crea el atajo de color fijo?
 *
 * Solo se reconocen los que llevan **el nombre que genera esta UI**, y no
 * cualquier `STATIC` de un paso: reutilizar un efecto que el usuario creo y
 * nombro a mano cambiaria la referencia de su escena por sorpresa, y editar
 * aquel efecto pasaria a afectar a esta.
 */
export function isGeneratedStaticEffect(effect: Effect): boolean {
  const [step, ...rest] = effect.steps
  if (effect.type !== 'STATIC' || step === undefined || rest.length > 0) return false
  return effect.name === staticEffectName(step.color)
}

/** El efecto generado para este color exacto, si ya esta en el catalogo. */
export function findStaticEffect(
  effects: readonly Effect[],
  color: RGBColor,
): Effect | undefined {
  const name = staticEffectName(color)
  return effects.find((effect) => effect.name === name && isGeneratedStaticEffect(effect))
}

/** Color de un efecto generado por el atajo, o `null` si no lo es. */
export function staticEffectColor(effect: Effect): RGBColor | null {
  return isGeneratedStaticEffect(effect) ? (effect.steps[0]?.color ?? null) : null
}

/**
 * Escena nueva: un objetivo sobre el dispositivo indicado y un color fijo.
 *
 * Arranca en color fijo y no en un efecto del catalogo porque es lo unico que
 * se puede rellenar sin saber que hay guardado, y porque es la escena que casi
 * todo el mundo crea primero. Sin dispositivo no hay objetivo posible: el
 * borrador sale vacio y la validacion lo explica.
 */
export function newSceneDraft(deviceId: string | null): SceneDraft {
  return {
    name: '',
    description: null,
    icon: null,
    isFavorite: false,
    targets: deviceId === null ? [] : [newTargetDraft(deviceId)],
  }
}

export function newTargetDraft(deviceId: string): SceneTargetDraft {
  return {
    deviceId,
    source: { kind: 'color', color: DEFAULT_SCENE_COLOR },
    enabled: true,
    brightness: null,
    speed: null,
  }
}

/**
 * Abre una escena guardada en el editor.
 *
 * Un objetivo se enseña como "color fijo" **solo** si el efecto al que apunta
 * es uno de los que genero este atajo; cualquier otro se enseña como lo que es,
 * una referencia a un efecto del catalogo. Sin el catalogo cargado no se puede
 * saber, y entonces se conserva la referencia: es lo unico que no inventa nada.
 */
export function draftFromScene(scene: Scene, effects: readonly Effect[]): SceneDraft {
  return {
    name: scene.name,
    description: scene.description,
    icon: scene.icon,
    isFavorite: scene.isFavorite,
    targets: scene.targets.map((target) => ({
      deviceId: target.deviceId,
      source: sourceOf(target, effects),
      enabled: target.enabled,
      brightness: target.brightness,
      speed: target.speed,
    })),
  }
}

function sourceOf(target: SceneTarget, effects: readonly Effect[]): SceneSource {
  const effect = effects.find((candidate) => candidate.id === target.effectId)
  const color = effect === undefined ? null : staticEffectColor(effect)
  return color === null ? { kind: 'effect', effectId: target.effectId } : { kind: 'color', color }
}

/**
 * Cuerpo de escritura de una escena que ya existe.
 *
 * Lo usa el interruptor de favorita: `PUT` es un reemplazo completo, asi que
 * cambiar una sola bandera obliga a reenviar la escena entera. Hacerlo desde la
 * copia autoritativa del servidor es lo unico que no borra nada por el camino.
 */
export function sceneWriteFrom(scene: Scene): SceneWrite {
  return {
    name: scene.name,
    description: scene.description,
    icon: scene.icon,
    isFavorite: scene.isFavorite,
    targets: scene.targets,
  }
}

export function withSceneTarget(
  draft: SceneDraft,
  index: number,
  target: SceneTargetDraft,
): SceneDraft {
  return {
    ...draft,
    targets: draft.targets.map((current, position) => (position === index ? target : current)),
  }
}

/** Un dispositivo no puede tener dos objetivos en la misma escena (422). */
export function usedDevices(draft: SceneDraft): ReadonlySet<string> {
  return new Set(draft.targets.map((target) => target.deviceId))
}

export function withAddedTarget(draft: SceneDraft, deviceId: string): SceneDraft {
  if (usedDevices(draft).has(deviceId)) return draft
  return { ...draft, targets: [...draft.targets, newTargetDraft(deviceId)] }
}

export function withRemovedTarget(draft: SceneDraft, index: number): SceneDraft {
  return { ...draft, targets: draft.targets.filter((_, position) => position !== index) }
}

/** Campos del editor que pueden llevar un mensaje de validacion. */
export type SceneDraftField = 'name' | 'targets'

export type SceneDraftErrors = Readonly<Partial<Record<SceneDraftField, string>>>

/**
 * Valida el borrador **antes** de enviarlo.
 *
 * No sustituye al servidor: comprueba lo que se puede explicar mejor aqui y
 * deja el resto a la respuesta del backend, que sigue siendo la autoridad.
 */
export function validateSceneDraft(draft: SceneDraft): SceneDraftErrors {
  const errors: { -readonly [K in SceneDraftField]?: string } = {}

  const name = draft.name.trim()
  if (name.length === 0) {
    errors.name = 'La escena necesita un nombre.'
  } else if (name.length > NAME_MAX_LENGTH) {
    errors.name = `El nombre no puede pasar de ${String(NAME_MAX_LENGTH)} caracteres.`
  }

  if (draft.targets.length === 0) {
    errors.targets =
      'Una escena necesita al menos un dispositivo con lo que debe reproducir. Da de alta un dispositivo si todavía no hay ninguno.'
  } else if (draft.targets.some((target) => target.source.kind === 'effect' && target.source.effectId === '')) {
    errors.targets = 'Elige qué efecto reproduce cada dispositivo.'
  }

  return errors
}

export function hasSceneErrors(errors: SceneDraftErrors): boolean {
  return Object.keys(errors).length > 0
}

/** Nombre de una escena del catalogo, o `null` si todavia no se ha cargado. */
export function sceneName(scenes: readonly Scene[], id: string): string | null {
  return scenes.find((scene) => scene.id === id)?.name ?? null
}

/**
 * Las escenas que merecen estar a un toque.
 *
 * El servidor ya devuelve el catalogo ordenado por nombre, asi que aqui solo se
 * filtra: reordenar lo dejaria distinto que en la lista completa sin motivo.
 */
export function favoriteScenes(scenes: readonly Scene[]): readonly Scene[] {
  return scenes.filter((scene) => scene.isFavorite)
}

/**
 * Que reproduce una escena, en una linea.
 *
 * Es lo que distingue dos escenas en la lista, igual que la paleta distingue
 * dos efectos. Sin el catalogo de efectos cargado no se nombra lo que no se
 * sabe: se cuenta cuantos objetivos hay.
 */
export function describeTargets(scene: Scene, effects: readonly Effect[]): string {
  if (scene.targets.length === 0) return 'Sin nada que reproducir todavía'

  const names = scene.targets.map((target) => {
    const effect = effects.find((candidate) => candidate.id === target.effectId)
    if (effect === undefined) return 'efecto desconocido'
    const color = staticEffectColor(effect)
    return color === null ? `«${effect.name}»` : `color fijo ${toHex(color)}`
  })

  return names.length === 1 ? capitalize(names[0] ?? '') : `${String(names.length)} dispositivos`
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
