import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiClient } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiClient.getHealth', () => {
  it('consulta la ruta relativa /api/v1/health', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiClient.getHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', expect.anything())
  })

  it('lanza ApiError con el codigo cuando el backend responde con error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))

    await expect(apiClient.getHealth()).rejects.toBeInstanceOf(ApiError)
  })
})

const DEVICE_BODY = {
  id: 'a1',
  name: 'Tira del salón',
  adapter_type: 'lotus_lantern_ble',
  address: 'AA:BB:CC:DD:EE:FF',
  enabled: true,
  auto_connect: false,
  connected: false,
  capabilities: {
    rgb: true,
    brightness: true,
    effects: false,
    addressable: false,
    segments: false,
    white_channel: false,
    music_mode: false,
  },
}

function stubJson(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('apiClient.scanDevices', () => {
  it('pide el escaneo con el tiempo maximo y devuelve dominio, no DTOs', async () => {
    const fetchMock = stubJson([{ name: 'ELK-BLEDOM', address: 'AA:BB', rssi: -55 }])

    await expect(apiClient.scanDevices(10)).resolves.toEqual([
      { name: 'ELK-BLEDOM', address: 'AA:BB', rssi: -55 },
    ])
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/devices/scan?timeout=10', expect.anything())
  })

  it('sin tiempo explicito no inventa uno: deja que mande el del servidor', async () => {
    const fetchMock = stubJson([])

    await apiClient.scanDevices()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/devices/scan', expect.anything())
  })

  it('propaga el 409 con su codigo para poder distinguir "ya hay un escaneo"', async () => {
    stubJson({ detail: { code: 'device_busy', message: 'scan in progress' } }, 409)

    await expect(apiClient.scanDevices(10)).rejects.toMatchObject({
      status: 409,
      code: 'device_busy',
    })
  })
})

describe('apiClient.registerDevice', () => {
  it('da de alta por direccion y devuelve el dispositivo ya en camelCase', async () => {
    const fetchMock = stubJson(DEVICE_BODY, 201)

    const device = await apiClient.registerDevice({ name: 'ELK-BLEDOM', address: 'AA:BB' })

    expect(device.adapterType).toBe('lotus_lantern_ble')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/devices',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'ELK-BLEDOM', address: 'AA:BB' }),
      }),
    )
  })

  it('omite el nombre cuando el anuncio no traia ninguno', async () => {
    const fetchMock = stubJson(DEVICE_BODY, 201)

    await apiClient.registerDevice({ name: null, address: 'AA:BB' })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/devices',
      expect.objectContaining({ body: JSON.stringify({ address: 'AA:BB' }) }),
    )
  })
})

const EFFECT_BODY = {
  id: 'e1',
  name: 'Atardecer',
  type: 'SMOOTH_CYCLE',
  description: null,
  loop: true,
  speed: 50,
  fps: 20,
  transition_ms: 2000,
  min_brightness: 0,
  max_brightness: 100,
  is_builtin: false,
  steps: [
    { position: 0, color: '#FF6A00', brightness: null, duration_ms: null, easing: null },
    { position: 1, color: '#7B00FF', brightness: 40, duration_ms: 500, easing: 'EASE_IN' },
  ],
}

describe('apiClient (efectos)', () => {
  it('traduce el catalogo a dominio, con el color ya como RGB', async () => {
    stubJson([EFFECT_BODY])

    const [effect] = await apiClient.listEffects()

    expect(effect?.transitionMs).toBe(2000)
    expect(effect?.steps[0]?.color).toEqual({ r: 255, g: 106, b: 0 })
    // Las anulaciones del paso se conservan: al reemplazar hay que devolverlas.
    expect(effect?.steps[1]).toMatchObject({ brightness: 40, durationMs: 500, easing: 'EASE_IN' })
  })

  it('escribe el cuerpo del contrato: hexadecimal, snake_case y sin id', async () => {
    const fetchMock = stubJson(EFFECT_BODY, 201)

    await apiClient.createEffect({
      name: '  Atardecer  ',
      type: 'SMOOTH_CYCLE',
      description: null,
      loop: true,
      speed: 50,
      fps: 20,
      transitionMs: 2000,
      minBrightness: 0,
      maxBrightness: 100,
      steps: [
        { color: { r: 255, g: 106, b: 0 }, brightness: null, durationMs: null, easing: null },
        { color: { r: 123, g: 0, b: 255 }, brightness: 40, durationMs: 500, easing: 'EASE_IN' },
      ],
    })

    const body: unknown = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body))
    expect(body).toMatchObject({
      // El nombre se recorta antes de salir.
      name: 'Atardecer',
      transition_ms: 2000,
      steps: [
        { color: '#FF6A00', brightness: null, duration_ms: null, easing: null },
        { color: '#7B00FF', brightness: 40, duration_ms: 500, easing: 'EASE_IN' },
      ],
    })
    expect(body).not.toHaveProperty('id')
  })

  it('un borrado responde 204 sin cuerpo y no se toma por un fallo', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiClient.deleteEffect('e1')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/effects/e1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('parar devuelve lo que suena DESPUES, que puede ser otro efecto', async () => {
    stubJson({ running: true, id: 'e2' })

    await expect(apiClient.stopEffect('e1')).resolves.toEqual({ id: 'e2' })
  })

  it('parar algo que ya no sonaba responde null, no un error', async () => {
    stubJson(null)

    await expect(apiClient.stopEffect('e1')).resolves.toBeNull()
  })
})

const SCENE_BODY = {
  id: 's1',
  name: 'Noche',
  description: 'Para leer',
  icon: 'moon',
  is_builtin: false,
  is_favorite: true,
  targets: [{ device_id: 'a1', effect_id: 'e1', brightness: 40, speed: null, enabled: true }],
}

describe('apiClient (escenas)', () => {
  it('traduce el catalogo a dominio, sin dejar claves crudas', async () => {
    stubJson([SCENE_BODY])

    await expect(apiClient.listScenes()).resolves.toEqual([
      {
        id: 's1',
        name: 'Noche',
        description: 'Para leer',
        icon: 'moon',
        isBuiltin: false,
        isFavorite: true,
        targets: [
          { deviceId: 'a1', effectId: 'e1', brightness: 40, speed: null, enabled: true },
        ],
      },
    ])
  })

  it('escribe el cuerpo del contrato: snake_case, sin id y con el nombre recortado', async () => {
    const fetchMock = stubJson(SCENE_BODY, 201)

    await apiClient.createScene({
      name: '  Noche  ',
      description: null,
      icon: null,
      isFavorite: true,
      targets: [{ deviceId: 'a1', effectId: 'e1', brightness: null, speed: null, enabled: true }],
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/scenes',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'Noche',
          description: null,
          icon: null,
          is_favorite: true,
          targets: [
            { device_id: 'a1', effect_id: 'e1', brightness: null, speed: null, enabled: true },
          ],
        }),
      }),
    )
  })

  it('duplicar con nombre lo manda; sin nombre no manda cuerpo', async () => {
    const named = stubJson(SCENE_BODY, 201)
    await apiClient.duplicateScene('s1', 'Otra')
    expect(named).toHaveBeenCalledWith(
      '/api/v1/scenes/s1/duplicate',
      expect.objectContaining({ body: JSON.stringify({ name: 'Otra' }) }),
    )

    vi.unstubAllGlobals()
    const plain = stubJson(SCENE_BODY, 201)
    await apiClient.duplicateScene('s1')
    expect(plain.mock.calls[0]?.[1]?.body).toBeUndefined()
  })

  it('propaga el 409 de una activacion con su codigo: no se activo nada', async () => {
    stubJson({ detail: { code: 'device_not_connected', message: 'x' } }, 409)

    await expect(apiClient.activateScene('s1')).rejects.toMatchObject({
      status: 409,
      code: 'device_not_connected',
    })
  })
})

describe('apiClient (perfiles)', () => {
  it('lee la escena predeterminada ya resuelta por el servidor', async () => {
    stubJson([
      {
        id: 'p1',
        name: 'Cine',
        description: null,
        icon: null,
        is_builtin: false,
        scenes: [
          { scene_id: 's1', position: 0, is_default: false },
          { scene_id: 's2', position: 1, is_default: true },
        ],
        default_scene_id: 's2',
      },
    ])

    const [profile] = await apiClient.listProfiles()

    expect(profile?.defaultSceneId).toBe('s2')
    expect(profile?.scenes[1]).toEqual({ sceneId: 's2', position: 1, isDefault: true })
  })

  it('escribe las escenas sin position: es el indice del array', async () => {
    const fetchMock = stubJson({
      id: 'p1',
      name: 'Cine',
      description: null,
      icon: null,
      is_builtin: false,
      scenes: [],
      default_scene_id: null,
    }, 201)

    await apiClient.createProfile({
      name: 'Cine',
      description: null,
      icon: null,
      scenes: [
        { sceneId: 's1', isDefault: false },
        { sceneId: 's2', isDefault: true },
      ],
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/profiles',
      expect.objectContaining({
        body: JSON.stringify({
          name: 'Cine',
          description: null,
          icon: null,
          scenes: [
            { scene_id: 's1', is_default: false },
            { scene_id: 's2', is_default: true },
          ],
        }),
      }),
    )
  })

  it('activar un perfil devuelve la escena que quedo puesta, no el perfil', async () => {
    stubJson({ profile_id: 'p1', scene: { id: 's2' } })

    await expect(apiClient.activateProfile('p1')).resolves.toEqual({ id: 's2' })
  })
})
