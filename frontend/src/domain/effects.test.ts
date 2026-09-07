import { describe, expect, it } from 'vitest'

import { rgb } from './color'
import {
  EFFECT_TYPE_SPECS,
  canAddStep,
  canRemoveStep,
  draftFromEffect,
  effectName,
  formatSeconds,
  hasErrors,
  newEffectDraft,
  speedFactor,
  transitionDurationMs,
  validateEffectDraft,
  withAddedStep,
  withBrightness,
  withEffectType,
  withRemovedStep,
  withStepColor,
  type Effect,
} from './effects'

/**
 * El dominio de efectos del cliente, que es donde vive todo lo que el editor
 * no debe decidir por su cuenta: las cotas de cada algoritmo, la aritmetica de
 * la velocidad y la validacion previa al envio.
 */

const EFFECT: Effect = {
  id: 'e1',
  name: 'Atardecer',
  type: 'SMOOTH_CYCLE',
  description: 'guardado por el usuario',
  loop: true,
  speed: 50,
  fps: 20,
  transitionMs: 2000,
  minBrightness: 10,
  maxBrightness: 90,
  isBuiltin: false,
  steps: [
    { color: rgb(255, 106, 0), brightness: null, durationMs: null, easing: null },
    { color: rgb(123, 0, 255), brightness: 40, durationMs: 500, easing: 'EASE_IN' },
  ],
}

describe('velocidad', () => {
  it('es un multiplicador simetrico, no una duracion', () => {
    // Misma formula que `speed_factor` del servidor.
    expect(speedFactor(0)).toBeCloseTo(2)
    expect(speedFactor(50)).toBeCloseTo(1)
    expect(speedFactor(100)).toBeCloseTo(0.5)
  })

  it('la duracion real sale de transitionMs, con la velocidad aplicada', () => {
    const draft = { transitionMs: 2000, speed: 50, fps: 20 }

    expect(transitionDurationMs(draft)).toBe(2000)
    expect(transitionDurationMs({ ...draft, speed: 100 })).toBe(1000)
    expect(transitionDurationMs({ ...draft, speed: 0 })).toBe(4000)
  })

  it('nunca baja de un fotograma, igual que el plan del servidor', () => {
    // 20 fps -> 50 ms por fotograma: una transicion mas corta no se veria.
    expect(transitionDurationMs({ transitionMs: 10, speed: 100, fps: 20 })).toBe(50)
  })

  it('se muestra en segundos, que es lo que una persona entiende', () => {
    expect(formatSeconds(1500)).toBe('1,5 s')
  })
})

describe('paleta', () => {
  it('cambiar de tipo recorta la paleta a lo que el algoritmo admite', () => {
    const draft = withEffectType(draftFromEffect(EFFECT), 'STATIC')

    expect(draft.steps).toHaveLength(1)
    expect(draft.steps[0]?.color).toEqual(rgb(255, 106, 0))
    // `STATIC` no es repetible: mantener el bucle guardaria algo que el
    // servidor ignoraria de todas formas.
    expect(draft.loop).toBe(false)
  })

  it('cambiar de tipo rellena la paleta cuando el algoritmo pide mas colores', () => {
    const single = withEffectType(draftFromEffect(EFFECT), 'PULSE')
    const cycle = withEffectType(single, 'SMOOTH_CYCLE')

    expect(single.steps).toHaveLength(1)
    expect(cycle.steps).toHaveLength(EFFECT_TYPE_SPECS.SMOOTH_CYCLE.minSteps)
    // Se repite el ultimo color en vez de inventar uno nuevo.
    expect(cycle.steps[1]?.color).toEqual(cycle.steps[0]?.color)
  })

  it('no deja quitar por debajo del minimo ni añadir por encima del maximo', () => {
    const fixed = withEffectType(draftFromEffect(EFFECT), 'STATIC')

    expect(canAddStep(fixed)).toBe(false)
    expect(canRemoveStep(fixed)).toBe(false)
    expect(withAddedStep(fixed).steps).toHaveLength(1)
    expect(withRemovedStep(fixed, 0).steps).toHaveLength(1)
  })

  it('editar un color conserva las anulaciones del paso', () => {
    const draft = withStepColor(draftFromEffect(EFFECT), 1, rgb(0, 0, 0))

    expect(draft.steps[1]).toEqual({
      color: rgb(0, 0, 0),
      brightness: 40,
      durationMs: 500,
      easing: 'EASE_IN',
    })
  })
})

describe('validacion', () => {
  it('acepta el borrador por defecto en cuanto tiene nombre', () => {
    expect(hasErrors(validateEffectDraft({ ...newEffectDraft(), name: 'Nuevo' }))).toBe(false)
  })

  it('exige un nombre', () => {
    // Un nombre de solo espacios pasaria el `min_length=1` del servidor y
    // quedaria guardado como un efecto sin nombre visible.
    expect(validateEffectDraft({ ...newEffectDraft(), name: '   ' }).name).toBe(
      'El efecto necesita un nombre.',
    )
  })

  it('exige los colores que el algoritmo necesita', () => {
    const draft = { ...newEffectDraft(), name: 'Ciclo', steps: [] }

    expect(validateEffectDraft(draft).palette).toBe('«Ciclo suave» necesita al menos 2 colores.')
  })

  it('impide un brillo minimo mayor que el maximo', () => {
    const draft = { ...newEffectDraft(), name: 'Pulso', minBrightness: 80, maxBrightness: 20 }

    expect(validateEffectDraft(draft).brightness).toBe(
      'El brillo mínimo no puede superar al máximo.',
    )
  })

  it('mover un extremo del brillo arrastra al otro en vez de dejarlo invalido', () => {
    const draft = withBrightness({ ...newEffectDraft(), maxBrightness: 40 }, 'min', 70)

    expect(draft).toMatchObject({ minBrightness: 70, maxBrightness: 70 })
    expect(hasErrors(validateEffectDraft({ ...draft, name: 'Pulso' }))).toBe(false)
  })
})

describe('effectName', () => {
  it('devuelve null cuando el catalogo todavia no se ha cargado', () => {
    expect(effectName([], 'e1')).toBeNull()
    expect(effectName([EFFECT], 'e1')).toBe('Atardecer')
  })
})
