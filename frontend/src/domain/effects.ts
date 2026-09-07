/**
 * Efectos en el dominio del cliente.
 *
 * Espejo de `EffectDefinition` del backend (backend/app/domain/effects/models.py)
 * con las mismas dos diferencias que el resto del dominio: color como
 * `RGBColor` en vez de `#RRGGBB` y claves en camelCase. La traduccion vive en
 * `api/dto.ts`.
 *
 * Tres cosas que este modulo existe para dejar claras, porque confundirlas es
 * facil y caro:
 *
 * 1. **El tipo es el algoritmo, la paleta son los colores.** `Sunset`,
 *    `Cyberpunk` o `Gaming` NO son tipos: son efectos guardados con
 *    `type = SMOOTH_CYCLE` y paletas distintas. Por eso la UI pide un tipo y
 *    una paleta por separado.
 * 2. **`speed` es un multiplicador, no una duracion.** La duracion la manda
 *    `transitionMs`; `speed` la escala con `2 ** ((50 - speed) / 50)`. Un
 *    usuario que ve "velocidad 100" no debe entender "100 ms", asi que la
 *    pantalla enseña siempre la duracion resultante (`transitionDurationMs`).
 * 3. **Cuantos pasos admite cada algoritmo lo declara el renderer del
 *    servidor.** `EFFECT_TYPE_SPECS` replica esas cotas para poder explicar el
 *    problema antes de enviarlo, pero el servidor sigue siendo la autoridad: si
 *    rechaza el efecto, se muestra su respuesta.
 */
import { rgb, type RGBColor } from './color'
import { BRIGHTNESS_MAX, BRIGHTNESS_MIN, clampBrightness } from './light'

/** Algoritmos con renderer en el servidor (`EffectType`). Contrato congelado. */
export const EFFECT_TYPES = ['STATIC', 'SMOOTH_CYCLE', 'PULSE', 'BREATH'] as const

export type EffectType = (typeof EFFECT_TYPES)[number]

export function isEffectType(value: unknown): value is EffectType {
  return typeof value === 'string' && (EFFECT_TYPES as readonly string[]).includes(value)
}

/** Curvas temporales (`Easing`). La UI no las edita todavia; si las conserva. */
export const EASINGS = ['LINEAR', 'EASE_IN', 'EASE_OUT', 'EASE_IN_OUT'] as const

export type Easing = (typeof EASINGS)[number]

export function isEasing(value: unknown): value is Easing {
  return typeof value === 'string' && (EASINGS as readonly string[]).includes(value)
}

/**
 * Un vertice del efecto.
 *
 * Los tres opcionales son **anulaciones**: `null` significa "usa lo del efecto",
 * no "usa cero". El editor no los ofrece, pero los conserva al reescribir
 * porque `PUT /effects/{id}` es un reemplazo completo y perderlos seria
 * destruir en silencio algo que el usuario no ha tocado.
 *
 * No lleva `position`: en el contrato de escritura **la posicion es el indice
 * del array** (backend/app/api/schemas/effects.py), asi que guardarla ademas
 * como campo permitiria representar un orden que contradijera al array.
 */
export interface EffectStep {
  readonly color: RGBColor
  readonly brightness: number | null
  readonly durationMs: number | null
  readonly easing: Easing | null
}

/** Un efecto guardado, tal y como lo publica `GET /effects`. */
export interface Effect {
  readonly id: string
  readonly name: string
  readonly type: EffectType
  readonly description: string | null
  readonly loop: boolean
  /** 0-100. Multiplicador de `transitionMs`, nunca una duracion. */
  readonly speed: number
  readonly fps: number
  /** Duracion base de UNA transicion entre dos vertices consecutivos. */
  readonly transitionMs: number
  /** Suelo de la envolvente de `PULSE` y `BREATH`. */
  readonly minBrightness: number
  /** Techo de la envolvente y brillo base de un paso sin brillo propio. */
  readonly maxBrightness: number
  /** Lo decide el servidor; no se envia al escribir. */
  readonly isBuiltin: boolean
  readonly steps: readonly EffectStep[]
}

/**
 * Lo que el editor manipula: un efecto **sin identidad**.
 *
 * Separado de `Effect` a proposito: un borrador todavia no existe en el
 * servidor y no tiene `id` ni `isBuiltin`, que los decide el. Colapsarlos
 * obligaria a inventar un id en el cliente, que es justo lo que el contrato de
 * `POST /effects` prohibe.
 */
export interface EffectDraft {
  readonly name: string
  readonly type: EffectType
  /** No se edita hoy; se conserva para no borrarla al reemplazar. */
  readonly description: string | null
  readonly loop: boolean
  readonly speed: number
  /** No se edita hoy; se conserva por el mismo motivo que `description`. */
  readonly fps: number
  readonly transitionMs: number
  readonly minBrightness: number
  readonly maxBrightness: number
  readonly steps: readonly EffectStep[]
}

/**
 * Lo que cada algoritmo admite y como se le explica al usuario.
 *
 * Replica las cuatro declaraciones de los renderers del servidor
 * (`min_steps`, `max_steps`, `loopable` y si usan envolvente de brillo). Es
 * duplicacion consciente y acotada: sin ella la UI solo podria enseñar el 422
 * despues de intentarlo, y un editor que no sabe cuantos colores caben no puede
 * deshabilitar «Añadir color».
 */
export interface EffectTypeSpec {
  readonly label: string
  /** Que hace, en una linea. Se lee bajo el selector de tipo. */
  readonly summary: string
  readonly minSteps: number
  /** `null` = sin tope. */
  readonly maxSteps: number | null
  readonly loopable: boolean
  /**
   * El brillo va y viene entre `minBrightness` y `maxBrightness`. En los tipos
   * que no la usan, `maxBrightness` es simplemente el brillo del efecto.
   */
  readonly brightnessEnvelope: boolean
}

export const EFFECT_TYPE_SPECS: Readonly<Record<EffectType, EffectTypeSpec>> = {
  STATIC: {
    label: 'Fijo',
    summary: 'Un solo color, sin animación. No consume enlace mientras dura.',
    minSteps: 1,
    maxSteps: 1,
    loopable: false,
    brightnessEnvelope: false,
  },
  SMOOTH_CYCLE: {
    label: 'Ciclo suave',
    summary:
      'Recorre la paleta con transiciones suaves. La tira muestra un color a la vez: la mezcla es temporal, no un degradado a lo largo de la tira.',
    minSteps: 2,
    maxSteps: null,
    loopable: true,
    brightnessEnvelope: false,
  },
  PULSE: {
    label: 'Pulso',
    summary: 'Un color fijo cuyo brillo sube y baja entre el mínimo y el máximo.',
    minSteps: 1,
    maxSteps: 1,
    loopable: true,
    brightnessEnvelope: true,
  },
  BREATH: {
    label: 'Respiración',
    summary:
      'Respira recorriendo la paleta: el color cambia en la parte oscura de cada respiración.',
    minSteps: 1,
    maxSteps: null,
    loopable: true,
    brightnessEnvelope: true,
  },
}

export const SPEED_MIN = 0
export const SPEED_MAX = 100
/** Velocidad neutra: factor x1. */
export const NEUTRAL_SPEED = 50

/** Tope del control de duracion. El servidor acepta cualquier entero >= 0. */
export const TRANSITION_MAX_MS = 10_000
export const TRANSITION_STEP_MS = 100

/** `effects.name` es `VARCHAR(120)` con `min_length=1` en el contrato. */
export const NAME_MAX_LENGTH = 120

/** Valor por defecto de `fps` en el contrato de escritura. */
export const DEFAULT_FPS = 20

/**
 * Multiplicador de duracion para una velocidad 0-100.
 *
 * Misma formula que `speed_factor` del servidor: exponencial y simetrica, con 0
 * al doble de duracion, 50 igual y 100 a la mitad.
 */
export function speedFactor(speed: number): number {
  return 2 ** ((NEUTRAL_SPEED - speed) / NEUTRAL_SPEED)
}

/** Duracion nominal de un fotograma, como `frame_duration_ms` del servidor. */
export function frameDurationMs(fps: number): number {
  return Math.round(1000 / fps)
}

/**
 * Duracion REAL de una transicion con la velocidad ya aplicada.
 *
 * Es lo que se enseña junto al control de velocidad: sin esto, "velocidad 100"
 * se lee como una duracion y el usuario no tiene forma de saber que la
 * autoridad la tiene `transitionMs`. El suelo de un fotograma es el mismo que
 * aplica el servidor al construir el plan.
 */
export function transitionDurationMs(
  draft: Pick<EffectDraft, 'transitionMs' | 'speed' | 'fps'>,
): number {
  return Math.max(
    frameDurationMs(draft.fps),
    Math.round(draft.transitionMs * speedFactor(draft.speed)),
  )
}

const SECONDS_FORMAT = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

/** `1500` -> `"1,5 s"`. Los milisegundos crudos no dicen nada a simple vista. */
export function formatSeconds(milliseconds: number): string {
  return `${SECONDS_FORMAT.format(milliseconds / 1000)} s`
}

/** Factor con dos decimales: `x1,00`. */
const FACTOR_FORMAT = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatSpeedFactor(speed: number): string {
  return `x${FACTOR_FORMAT.format(speedFactor(speed))}`
}

/** Paleta inicial de un efecto nuevo: dos colores que se distinguen de verdad. */
const DEFAULT_PALETTE: readonly RGBColor[] = [rgb(0, 157, 255), rgb(255, 0, 140)]

function plainStep(color: RGBColor): EffectStep {
  return { color, brightness: null, durationMs: null, easing: null }
}

/**
 * Borrador de un efecto nuevo.
 *
 * Arranca en `SMOOTH_CYCLE` porque es el tipo del que salen casi todos los
 * efectos del catalogo; `name` vacio a proposito, para que el editor no proponga
 * un nombre que el usuario acabe guardando sin leer.
 */
export function newEffectDraft(): EffectDraft {
  return {
    name: '',
    type: 'SMOOTH_CYCLE',
    description: null,
    loop: true,
    speed: NEUTRAL_SPEED,
    fps: DEFAULT_FPS,
    transitionMs: 1000,
    minBrightness: BRIGHTNESS_MIN,
    maxBrightness: BRIGHTNESS_MAX,
    steps: DEFAULT_PALETTE.map(plainStep),
  }
}

export function draftFromEffect(effect: Effect): EffectDraft {
  return {
    name: effect.name,
    type: effect.type,
    description: effect.description,
    loop: effect.loop,
    speed: effect.speed,
    fps: effect.fps,
    transitionMs: effect.transitionMs,
    minBrightness: effect.minBrightness,
    maxBrightness: effect.maxBrightness,
    steps: effect.steps,
  }
}

/**
 * Cambia el algoritmo y **adapta la paleta a sus cotas**.
 *
 * Pasar a `STATIC` con cuatro colores dejaria un borrador que el servidor
 * rechazaria con un 422; recortar aqui hace que ese estado no llegue a existir.
 * Se recorta por el final y se rellena repitiendo el ultimo color, que es lo
 * unico que no inventa un color que el usuario no eligio.
 */
export function withEffectType(draft: EffectDraft, type: EffectType): EffectDraft {
  const spec = EFFECT_TYPE_SPECS[type]
  const steps = [...draft.steps]

  if (spec.maxSteps !== null && steps.length > spec.maxSteps) steps.length = spec.maxSteps
  while (steps.length < spec.minSteps) steps.push(plainStep(lastColor(steps)))

  return { ...draft, type, steps, loop: spec.loopable && draft.loop }
}

export function withStepColor(draft: EffectDraft, index: number, color: RGBColor): EffectDraft {
  return {
    ...draft,
    steps: draft.steps.map((step, position) => (position === index ? { ...step, color } : step)),
  }
}

export function canAddStep(draft: EffectDraft): boolean {
  const { maxSteps } = EFFECT_TYPE_SPECS[draft.type]
  return maxSteps === null || draft.steps.length < maxSteps
}

export function canRemoveStep(draft: EffectDraft): boolean {
  return draft.steps.length > EFFECT_TYPE_SPECS[draft.type].minSteps
}

/** Añade repitiendo el ultimo color: el usuario lo cambia, no lo adivina la UI. */
export function withAddedStep(draft: EffectDraft): EffectDraft {
  if (!canAddStep(draft)) return draft
  return { ...draft, steps: [...draft.steps, plainStep(lastColor(draft.steps))] }
}

export function withRemovedStep(draft: EffectDraft, index: number): EffectDraft {
  if (!canRemoveStep(draft)) return draft
  return { ...draft, steps: draft.steps.filter((_, position) => position !== index) }
}

/** El brillo minimo nunca puede superar al maximo: el servidor lo rechaza. */
export function withBrightness(
  draft: EffectDraft,
  bound: 'min' | 'max',
  value: number,
): EffectDraft {
  const clamped = clampBrightness(value)
  return bound === 'min'
    ? { ...draft, minBrightness: clamped, maxBrightness: Math.max(clamped, draft.maxBrightness) }
    : { ...draft, maxBrightness: clamped, minBrightness: Math.min(clamped, draft.minBrightness) }
}

/** Campos del editor que pueden llevar un mensaje de validacion. */
export type EffectDraftField = 'name' | 'palette' | 'brightness'

export type EffectDraftErrors = Readonly<Partial<Record<EffectDraftField, string>>>

/**
 * Valida el borrador **antes** de enviarlo.
 *
 * No sustituye al servidor: comprueba lo que se puede explicar mejor aqui (que
 * un ciclo suave necesita dos colores) y deja el resto a la respuesta del
 * backend, que sigue siendo la autoridad.
 */
export function validateEffectDraft(draft: EffectDraft): EffectDraftErrors {
  const errors: { -readonly [K in EffectDraftField]?: string } = {}
  const spec = EFFECT_TYPE_SPECS[draft.type]

  const name = draft.name.trim()
  if (name.length === 0) {
    errors.name = 'El efecto necesita un nombre.'
  } else if (name.length > NAME_MAX_LENGTH) {
    errors.name = `El nombre no puede pasar de ${String(NAME_MAX_LENGTH)} caracteres.`
  }

  if (draft.steps.length < spec.minSteps) {
    errors.palette =
      spec.minSteps === 1
        ? `«${spec.label}» necesita al menos un color.`
        : `«${spec.label}» necesita al menos ${String(spec.minSteps)} colores.`
  } else if (spec.maxSteps !== null && draft.steps.length > spec.maxSteps) {
    errors.palette =
      spec.maxSteps === 1
        ? `«${spec.label}» admite un solo color.`
        : `«${spec.label}» admite como mucho ${String(spec.maxSteps)} colores.`
  }

  if (draft.minBrightness > draft.maxBrightness) {
    errors.brightness = 'El brillo mínimo no puede superar al máximo.'
  }

  return errors
}

export function hasErrors(errors: EffectDraftErrors): boolean {
  return Object.keys(errors).length > 0
}

/** Nombre de un efecto del catalogo, o `null` si todavia no se ha cargado. */
export function effectName(effects: readonly Effect[], id: string): string | null {
  return effects.find((effect) => effect.id === id)?.name ?? null
}

/** Blanco solo si no hay ningun color del que partir (paleta vacia). */
function lastColor(steps: readonly EffectStep[]): RGBColor {
  return steps.at(-1)?.color ?? rgb(255, 255, 255)
}
