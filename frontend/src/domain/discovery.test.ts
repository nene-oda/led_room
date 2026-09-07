import { describe, expect, it } from 'vitest'

import type { DiscoveredDevice } from './devices'
import {
  maskAddress,
  radioStatus,
  scanTimeoutOf,
  signalStrength,
  sortByProximity,
  SCAN_TIMEOUT_SECONDS,
} from './discovery'
import type { SystemInfo } from './system'

function server(supportsDiscovery: boolean, scanTimeoutSeconds = 10): SystemInfo {
  return { adapterType: 'null', supportsDiscovery, scanTimeoutSeconds }
}

function seen(address: string, rssi: number | null): DiscoveredDevice {
  return { name: null, address, rssi }
}

describe('signalStrength', () => {
  it('traduce el RSSI a tres tramos anchos', () => {
    expect(signalStrength(-40)).toBe('near')
    expect(signalStrength(-60)).toBe('near')
    expect(signalStrength(-61)).toBe('medium')
    expect(signalStrength(-75)).toBe('medium')
    expect(signalStrength(-76)).toBe('far')
  })

  it('no inventa cercania cuando el anuncio no trae RSSI', () => {
    expect(signalStrength(null)).toBe('unknown')
    expect(signalStrength(Number.NaN)).toBe('unknown')
  })
})

describe('sortByProximity', () => {
  it('pone delante lo mas cercano y al final lo que no publica RSSI', () => {
    const ordered = sortByProximity([seen('c', null), seen('b', -80), seen('a', -35)])

    expect(ordered.map((device) => device.address)).toEqual(['a', 'b', 'c'])
  })

  it('devuelve una copia: la lista original no se toca', () => {
    const original = [seen('b', -80), seen('a', -35)]
    sortByProximity(original)

    expect(original.map((device) => device.address)).toEqual(['b', 'a'])
  })
})

describe('maskAddress', () => {
  it('oculta el centro de una MAC y de un GUID', () => {
    expect(maskAddress('AA:BB:CC:DD:EE:FF')).toBe('AA:B…E:FF')
    expect(maskAddress('12345678-90ab-cdef-1234-567890abcdef')).toBe('1234…cdef')
  })

  it('deja intactas las direcciones demasiado cortas para ocultar nada', () => {
    expect(maskAddress('AA:BB')).toBe('AA:BB')
  })
})

describe('radioStatus', () => {
  it('distingue «no puede» de «todavia no lo ha dicho»', () => {
    // El tercer estado es el que evita el peor error posible: deshabilitar el
    // descubrimiento en un servidor que si tiene radio solo porque la respuesta
    // aun no ha llegado.
    expect(radioStatus(null)).toBe('unknown')
    expect(radioStatus(server(true))).toBe('available')
    expect(radioStatus(server(false))).toBe('missing')
  })
})

describe('scanTimeoutOf', () => {
  it('manda el techo del servidor; el del cliente es solo respaldo', () => {
    expect(scanTimeoutOf(server(true, 25))).toBe(25)
    expect(scanTimeoutOf(null)).toBe(SCAN_TIMEOUT_SECONDS)
  })
})
