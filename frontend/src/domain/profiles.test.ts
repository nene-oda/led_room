import { describe, expect, it } from 'vitest'

import {
  defaultSceneOf,
  draftFromProfile,
  includesScene,
  newProfileDraft,
  validateProfileDraft,
  withDefaultScene,
  withScene,
  type Profile,
} from './profiles'

function profile(overrides: Partial<Profile>): Profile {
  return {
    id: 'p1',
    name: 'Cine',
    description: null,
    icon: null,
    isBuiltin: false,
    scenes: [{ sceneId: 's1', position: 0, isDefault: true }],
    defaultSceneId: 's1',
    ...overrides,
  }
}

describe('borrador de perfil', () => {
  it('parte de la escena que el SERVIDOR daba por predeterminada', () => {
    // El servidor publica `defaultSceneId` ya resuelto. Si el editor mirase las
    // banderas crudas, un perfil sin ninguna marcada enseñaria una cosa y el
    // servidor activaria otra.
    const draft = draftFromProfile(
      profile({
        scenes: [
          { sceneId: 's1', position: 0, isDefault: false },
          { sceneId: 's2', position: 1, isDefault: false },
        ],
        defaultSceneId: 's2',
      }),
    )

    expect(defaultSceneOf(draft)).toBe('s2')
  })

  it('la primera escena que se añade queda predeterminada sin tener que elegirla', () => {
    const draft = withScene(newProfileDraft(), 's1', true)

    expect(includesScene(draft, 's1')).toBe(true)
    expect(defaultSceneOf(draft)).toBe('s1')
  })

  it('quitar la predeterminada pasa la marca a la que queda', () => {
    const draft = withScene(withScene(newProfileDraft(), 's1', true), 's2', true)

    expect(defaultSceneOf(withScene(draft, 's1', false))).toBe('s2')
  })

  it('marcar una predeterminada desmarca a las demas: solo puede haber una', () => {
    const draft = withDefaultScene(
      withScene(withScene(newProfileDraft(), 's1', true), 's2', true),
      's2',
    )

    expect(draft.scenes.filter((link) => link.isDefault)).toHaveLength(1)
    expect(defaultSceneOf(draft)).toBe('s2')
  })

  it('no se puede predeterminar una escena que no esta en el perfil', () => {
    const draft = withDefaultScene(newProfileDraft(), 's9')

    expect(draft.scenes).toHaveLength(0)
  })

  it('un perfil sin escenas se rechaza aqui: activarlo responderia 409', () => {
    const errors = validateProfileDraft({ ...newProfileDraft(), name: 'Cine' })

    expect(errors.scenes).toContain('al menos una escena')
  })

  it('exige nombre', () => {
    expect(validateProfileDraft(newProfileDraft()).name).toBe('El perfil necesita un nombre.')
  })
})
