import { describe, expect, it } from 'vitest'

import { rgb } from './color'
import type { Effect } from './effects'
import {
  describeTargets,
  draftFromScene,
  favoriteScenes,
  findStaticEffect,
  isGeneratedStaticEffect,
  newSceneDraft,
  sceneWriteFrom,
  staticEffectDraft,
  staticEffectName,
  usedDevices,
  validateSceneDraft,
  withAddedTarget,
  type Scene,
} from './scenes'

const AMBER = rgb(255, 147, 41)

function effect(overrides: Partial<Effect>): Effect {
  return {
    id: 'e1',
    name: 'Atardecer',
    type: 'SMOOTH_CYCLE',
    description: null,
    loop: true,
    speed: 50,
    fps: 20,
    transitionMs: 1000,
    minBrightness: 0,
    maxBrightness: 100,
    isBuiltin: false,
    steps: [{ color: rgb(255, 0, 0), brightness: null, durationMs: null, easing: null }],
    ...overrides,
  }
}

function scene(overrides: Partial<Scene>): Scene {
  return {
    id: 's1',
    name: 'Noche',
    description: null,
    icon: null,
    isBuiltin: false,
    isFavorite: false,
    targets: [{ deviceId: 'a1', effectId: 'e1', brightness: null, speed: null, enabled: true }],
    ...overrides,
  }
}

describe('el atajo de color fijo', () => {
  it('construye un efecto STATIC de un solo paso con el color elegido', () => {
    const draft = staticEffectDraft(AMBER)

    expect(draft.type).toBe('STATIC')
    expect(draft.steps).toHaveLength(1)
    expect(draft.steps[0]?.color).toEqual(AMBER)
    // El nombre es lo que se le enseña al usuario ANTES de guardar: si cambia
    // aqui, cambia lo que la pantalla prometio.
    expect(draft.name).toBe('Color fijo #FF9329')
    expect(draft.loop).toBe(false)
  })

  it('reutiliza el efecto que ya se genero para ese color exacto', () => {
    const generated = effect({
      id: 'e9',
      name: staticEffectName(AMBER),
      type: 'STATIC',
      steps: [{ color: AMBER, brightness: null, durationMs: null, easing: null }],
    })

    expect(findStaticEffect([generated], AMBER)?.id).toBe('e9')
    expect(findStaticEffect([generated], rgb(0, 0, 255))).toBeUndefined()
  })

  it('no se apropia de un efecto STATIC que nombro el usuario', () => {
    // Mismo tipo, mismo color, otro nombre: reutilizarlo cambiaria por sorpresa
    // la referencia de la escena y editarlo pasaria a afectarla.
    const mine = effect({
      name: 'Mi naranja',
      type: 'STATIC',
      steps: [{ color: AMBER, brightness: null, durationMs: null, easing: null }],
    })

    expect(isGeneratedStaticEffect(mine)).toBe(false)
    expect(findStaticEffect([mine], AMBER)).toBeUndefined()
  })
})

describe('borrador de escena', () => {
  it('una escena nueva apunta al dispositivo indicado con un color fijo', () => {
    const draft = newSceneDraft('a1')

    expect(draft.targets).toHaveLength(1)
    expect(draft.targets[0]?.deviceId).toBe('a1')
    expect(draft.targets[0]?.source.kind).toBe('color')
  })

  it('sin dispositivo no inventa ningun objetivo, y la validacion lo explica', () => {
    const draft = newSceneDraft(null)

    expect(draft.targets).toHaveLength(0)
    expect(validateSceneDraft({ ...draft, name: 'Noche' }).targets).toContain(
      'al menos un dispositivo',
    )
  })

  it('exige nombre', () => {
    expect(validateSceneDraft(newSceneDraft('a1')).name).toBe('La escena necesita un nombre.')
    expect(validateSceneDraft({ ...newSceneDraft('a1'), name: '  Noche  ' }).name).toBeUndefined()
  })

  it('no deja añadir dos objetivos al mismo dispositivo (seria un 422)', () => {
    const draft = withAddedTarget(newSceneDraft('a1'), 'a1')

    expect(draft.targets).toHaveLength(1)
    expect([...usedDevices(draft)]).toEqual(['a1'])
  })

  it('al abrir una escena, un efecto generado se enseña como color y otro como efecto', () => {
    const generated = effect({
      id: 'e9',
      name: staticEffectName(AMBER),
      type: 'STATIC',
      steps: [{ color: AMBER, brightness: null, durationMs: null, easing: null }],
    })
    const saved = scene({
      targets: [
        { deviceId: 'a1', effectId: 'e9', brightness: null, speed: null, enabled: true },
        { deviceId: 'a2', effectId: 'e1', brightness: 50, speed: 70, enabled: false },
      ],
    })

    const draft = draftFromScene(saved, [generated, effect({})])

    expect(draft.targets[0]?.source).toEqual({ kind: 'color', color: AMBER })
    expect(draft.targets[1]?.source).toEqual({ kind: 'effect', effectId: 'e1' })
    // Lo que el editor no ofrece, lo conserva: `PUT` reemplaza la escena entera.
    expect(draft.targets[1]?.brightness).toBe(50)
    expect(draft.targets[1]?.speed).toBe(70)
    expect(draft.targets[1]?.enabled).toBe(false)
  })

  it('el cuerpo de escritura no lleva ni id ni is_builtin', () => {
    const write = sceneWriteFrom(scene({ isFavorite: true }))

    expect(write).not.toHaveProperty('id')
    expect(write).not.toHaveProperty('isBuiltin')
    expect(write.isFavorite).toBe(true)
  })
})

describe('lectura del catalogo', () => {
  it('las favoritas conservan el orden del servidor', () => {
    const scenes = [
      scene({ id: 'a', name: 'Alba', isFavorite: true }),
      scene({ id: 'b', name: 'Bosque' }),
      scene({ id: 'c', name: 'Cine', isFavorite: true }),
    ]

    expect(favoriteScenes(scenes).map((item) => item.id)).toEqual(['a', 'c'])
  })

  it('cuenta que reproduce, nombrando el efecto o el color', () => {
    const generated = effect({
      id: 'e9',
      name: staticEffectName(AMBER),
      type: 'STATIC',
      steps: [{ color: AMBER, brightness: null, durationMs: null, easing: null }],
    })

    expect(describeTargets(scene({}), [effect({})])).toBe('«Atardecer»')
    expect(
      describeTargets(
        scene({ targets: [{ deviceId: 'a1', effectId: 'e9', brightness: null, speed: null, enabled: true }] }),
        [generated],
      ),
    ).toBe('Color fijo #FF9329')
    expect(describeTargets(scene({ targets: [] }), [])).toBe('Sin nada que reproducir todavía')
  })
})
