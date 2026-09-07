import { describe, expect, it, vi } from 'vitest'

import {
  brightnessCommand,
  colorCommand,
  fromNewDevice,
  toDiscoveredDevice,
  parseServerEvent,
  powerCommand,
  toDevice,
  toErrorCode,
  toGlobalState,
  toSystemInfo,
  type DeviceDto,
  type GlobalStateDto,
} from './dto'
import { rgb } from '../domain/color'
import { SCAN_TIMEOUT_SECONDS } from '../domain/discovery'

const DEVICE: DeviceDto = {
  id: 'a1',
  name: 'Tira del salón',
  adapter_type: 'null',
  address: 'AA:BB',
  enabled: true,
  auto_connect: true,
  connected: true,
  capabilities: {
    rgb: true,
    brightness: false,
    effects: true,
    addressable: false,
    segments: false,
    white_channel: false,
    music_mode: false,
  },
}

const STATE: GlobalStateDto = {
  version: 7,
  device: { device_id: 'a1', connected: true, rssi: -55, last_error: null },
  light: { power: true, color: '#7B00FF', brightness: 60 },
  effect: null,
  scene: null,
}

describe('mapeo del cable al dominio', () => {
  it('traduce snake_case a camelCase sin dejar claves crudas', () => {
    const device = toDevice(DEVICE)

    expect(device.adapterType).toBe('null')
    expect(device.autoConnect).toBe(true)
    expect(device.capabilities.whiteChannel).toBe(false)
    expect(device.capabilities.musicMode).toBe(false)
    expect(Object.keys(device.capabilities)).not.toContain('white_channel')
  })

  it('convierte el color de lectura #RRGGBB en RGBColor', () => {
    expect(toGlobalState(STATE).light.color).toEqual(rgb(123, 0, 255))
  })

  it('normaliza las claves ausentes a null en vez de undefined', () => {
    const state = toGlobalState({ version: 1, light: { power: false, color: '#000000', brightness: 0 } })
    expect(state.device).toBeNull()

    // La clave se omite en vez de mandar `undefined`: es lo que haria un
    // backend con `exclude_none`, y es el caso que el DTO tiene que tolerar.
    const withoutAddress: DeviceDto = {
      id: DEVICE.id,
      name: DEVICE.name,
      adapter_type: DEVICE.adapter_type,
      enabled: DEVICE.enabled,
      auto_connect: DEVICE.auto_connect,
      connected: DEVICE.connected,
      capabilities: DEVICE.capabilities,
    }
    expect(toDevice(withoutAddress).address).toBeNull()
  })
})

describe('mapeo del dominio al cable', () => {
  it('manda el color como {r,g,b} en los comandos, nunca como hexadecimal', () => {
    expect(colorCommand(rgb(1, 2, 3))).toEqual({ type: 'light.color', payload: { r: 1, g: 2, b: 3 } })
  })

  it('recorta el brillo al rango publicado antes de enviarlo', () => {
    expect(brightnessCommand(140)).toEqual({ type: 'light.brightness', payload: { brightness: 100 } })
    expect(powerCommand(true)).toEqual({ type: 'light.power', payload: { on: true } })
  })
})

describe('toErrorCode', () => {
  it('extrae el codigo estable del cuerpo uniforme de error', () => {
    expect(toErrorCode({ detail: { code: 'device_not_connected', message: 'x' } })).toBe(
      'device_not_connected',
    )
  })

  it('devuelve null con el cuerpo por defecto de FastAPI de una ruta inexistente', () => {
    expect(toErrorCode({ detail: 'Not Found' })).toBeNull()
    expect(toErrorCode('vaya')).toBeNull()
  })
})

describe('parseServerEvent', () => {
  it('conserva la version del sobre, que es lo que ordena los frames', () => {
    const event = parseServerEvent(
      JSON.stringify({ type: 'light.brightness.changed', version: 12, payload: { brightness: 40 } }),
    )

    expect(event).toEqual({ kind: 'brightness', brightness: 40, version: 12 })
  })

  it('acepta un frame sin version (backend anterior al sobre corregido)', () => {
    const event = parseServerEvent(JSON.stringify({ type: 'light.power.changed', payload: { power: true } }))

    expect(event).toEqual({ kind: 'power', power: true, version: null })
  })

  it('traduce el snapshot a estado global de dominio', () => {
    const event = parseServerEvent(
      JSON.stringify({ type: 'state.snapshot', version: 7, payload: STATE }),
    )

    expect(event).toEqual({
      kind: 'snapshot',
      version: 7,
      state: {
        version: 7,
        device: { deviceId: 'a1', connected: true, rssi: -55, lastError: null },
        light: { power: true, color: rgb(123, 0, 255), brightness: 60 },
        // La ranura de efecto ya se mapea (Fase 5): `null` = no suena nada.
        effect: null,
        // Y la de escena desde la Fase 6, con la misma regla.
        scene: null,
      },
    })
  })

  it('lee la escena activada, que es lo que resalta la escena en marcha', () => {
    const event = parseServerEvent(
      JSON.stringify({ type: 'scene.activated', version: 9, payload: { scene_id: 's1' } }),
    )

    expect(event).toEqual({ kind: 'scene', sceneId: 's1', version: 9 })
  })

  it('ignora los eventos que esta version de la UI no pinta', () => {
    expect(parseServerEvent(JSON.stringify({ type: 'device.renamed', payload: { id: 'a1' } }))).toBeNull()
  })

  it('no lanza con un frame ilegible, pero deja constancia', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    expect(parseServerEvent('{no es json')).toBeNull()
    expect(warn).toHaveBeenCalled()

    warn.mockRestore()
  })
})

describe('mapeo del descubrimiento', () => {
  it('normaliza a null lo que el anuncio BLE no trae', () => {
    expect(toDiscoveredDevice({ address: 'AA:BB' })).toEqual({
      name: null,
      address: 'AA:BB',
      rssi: null,
    })
  })

  it('conserva nombre y rssi cuando vienen', () => {
    expect(toDiscoveredDevice({ name: 'ELK-BLEDOM', address: 'AA:BB', rssi: -70 })).toEqual({
      name: 'ELK-BLEDOM',
      address: 'AA:BB',
      rssi: -70,
    })
  })

  it('no manda adapter_type en el alta: lo elige el servidor', () => {
    expect(fromNewDevice({ name: 'ELK-BLEDOM', address: 'AA:BB' })).toEqual({
      name: 'ELK-BLEDOM',
      address: 'AA:BB',
    })
  })

  it('omite la clave name en vez de mandar null', () => {
    expect(Object.keys(fromNewDevice({ name: null, address: 'AA:BB' }))).toEqual(['address'])
  })
})

describe('toSystemInfo', () => {
  it('traduce la respuesta del servidor a dominio', () => {
    expect(
      toSystemInfo({ adapter_type: 'null', supports_discovery: false, scan_timeout_seconds: 15 }),
    ).toEqual({ adapterType: 'null', supportsDiscovery: false, scanTimeoutSeconds: 15 })
  })

  it('sin `supports_discovery` no afirma nada: devuelve null', () => {
    // De este valor depende que se deshabilite el boton de buscar. Inventarlo en
    // cualquiera de los dos sentidos es peor que admitir que no se sabe, y es lo
    // unico que protege a la UI de un cambio de contrato del backend.
    expect(toSystemInfo({ adapter_type: 'null' })).toBeNull()
    expect(toSystemInfo({ supports_discovery: 'no' })).toBeNull()
    expect(toSystemInfo(null)).toBeNull()
    expect(toSystemInfo([])).toBeNull()
  })

  it('completa lo accesorio en vez de rechazar la respuesta entera', () => {
    // El nombre del adaptador solo se enseña y el timeout tiene respaldo en el
    // dominio: perderlos no justifica tirar el dato por el que se preguntaba.
    expect(toSystemInfo({ supports_discovery: true })).toEqual({
      adapterType: null,
      supportsDiscovery: true,
      scanTimeoutSeconds: SCAN_TIMEOUT_SECONDS,
    })
    expect(toSystemInfo({ supports_discovery: true, scan_timeout_seconds: 0 })).toEqual({
      adapterType: null,
      supportsDiscovery: true,
      scanTimeoutSeconds: SCAN_TIMEOUT_SECONDS,
    })
  })
})
