import { describe, expect, it } from 'vitest'

import { rgb } from './color'
import { hsvToRgb, normalizeHue, rgbToHsv } from './hsv'

describe('hsvToRgb', () => {
  it('devuelve los primarios en los vertices del circulo', () => {
    expect(hsvToRgb({ h: 0, s: 1, v: 1 })).toEqual(rgb(255, 0, 0))
    expect(hsvToRgb({ h: 120, s: 1, v: 1 })).toEqual(rgb(0, 255, 0))
    expect(hsvToRgb({ h: 240, s: 1, v: 1 })).toEqual(rgb(0, 0, 255))
  })

  it('con saturacion 0 devuelve blanco sea cual sea el tono', () => {
    expect(hsvToRgb({ h: 42, s: 0, v: 1 })).toEqual(rgb(255, 255, 255))
  })

  it('normaliza tonos negativos y mayores de 360', () => {
    expect(hsvToRgb({ h: -120, s: 1, v: 1 })).toEqual(hsvToRgb({ h: 240, s: 1, v: 1 }))
    expect(hsvToRgb({ h: 480, s: 1, v: 1 })).toEqual(hsvToRgb({ h: 120, s: 1, v: 1 }))
  })
})

describe('rgbToHsv', () => {
  it('es inverso de hsvToRgb para los colores del selector', () => {
    // La tolerancia no es arbitraria: RGB tiene 8 bits por canal, asi que con
    // saturacion baja dos tonos vecinos caen en el mismo entero. El error
    // maximo es ~1 grado con s=0.25, imperceptible en el puntero del selector.
    for (const hue of [0, 37, 120, 210, 300, 359]) {
      for (const saturation of [0.25, 0.5, 1]) {
        const roundTrip = rgbToHsv(hsvToRgb({ h: hue, s: saturation, v: 1 }))
        expect(Math.abs(roundTrip.h - hue)).toBeLessThanOrEqual(1.5)
        expect(roundTrip.s).toBeCloseTo(saturation, 2)
      }
    }
  })

  it('devuelve tono 0 para un gris, donde el tono es indeterminado', () => {
    expect(rgbToHsv(rgb(128, 128, 128)).h).toBe(0)
  })
})

describe('normalizeHue', () => {
  it('rechaza valores no finitos en vez de propagar NaN al color', () => {
    expect(() => normalizeHue(Number.NaN)).toThrow(RangeError)
  })
})
