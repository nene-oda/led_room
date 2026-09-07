import { describe, expect, it } from 'vitest'

import { CHANNEL_MAX, CHANNEL_MIN, clampChannel, fromHex, rgb, toHex } from './color'

describe('toHex', () => {
  it('emite siempre mayusculas, que es lo que exige el CHECK de device_state', () => {
    expect(toHex({ r: 123, g: 0, b: 255 })).toBe('#7B00FF')
    expect(toHex({ r: 171, g: 205, b: 239 })).toBe('#ABCDEF')
  })

  it('rellena con cero a la izquierda cada canal', () => {
    expect(toHex({ r: 0, g: 1, b: 15 })).toBe('#00010F')
  })

  it('cubre los extremos del rango', () => {
    expect(toHex({ r: CHANNEL_MIN, g: CHANNEL_MIN, b: CHANNEL_MIN })).toBe('#000000')
    expect(toHex({ r: CHANNEL_MAX, g: CHANNEL_MAX, b: CHANNEL_MAX })).toBe('#FFFFFF')
  })

  it('recorta y redondea canales fuera de rango en vez de emitir hex invalido', () => {
    expect(toHex({ r: -5, g: 254.6, b: 300 })).toBe('#00FFFF')
  })
})

describe('fromHex', () => {
  it('acepta la forma canonica con almohadilla', () => {
    expect(fromHex('#7B00FF')).toEqual({ r: 123, g: 0, b: 255 })
  })

  it('acepta minusculas, sin almohadilla y con espacios alrededor', () => {
    expect(fromHex('  7b00ff  ')).toEqual({ r: 123, g: 0, b: 255 })
    expect(fromHex('#abcdef')).toEqual({ r: 171, g: 205, b: 239 })
  })

  it('cubre los extremos del rango', () => {
    expect(fromHex('#000000')).toEqual({ r: 0, g: 0, b: 0 })
    expect(fromHex('#FFFFFF')).toEqual({ r: 255, g: 255, b: 255 })
  })

  it.each(['', '#', '#FFF', '#12345', '#1234567', '#GGGGGG', '#7B00F', 'rgb(1,2,3)', '12 34 56'])(
    'rechaza la entrada invalida %o',
    (value) => {
      expect(() => fromHex(value)).toThrow(RangeError)
    },
  )
})

describe('ida y vuelta', () => {
  it.each(['#000000', '#FFFFFF', '#7B00FF', '#010203', '#22C55E'])(
    'fromHex y toHex se cancelan para %s',
    (hex) => {
      expect(toHex(fromHex(hex))).toBe(hex)
    },
  )

  it('normaliza a mayusculas al dar la vuelta a una entrada en minusculas', () => {
    expect(toHex(fromHex('#7b00ff'))).toBe('#7B00FF')
  })

  it('conserva el color al ir de {r,g,b} a hex y volver', () => {
    const color = rgb(12, 200, 34)
    expect(fromHex(toHex(color))).toEqual(color)
  })
})

describe('rgb / clampChannel', () => {
  it('redondea al entero mas cercano con los medios hacia arriba', () => {
    expect(clampChannel(127.4)).toBe(127)
    expect(clampChannel(127.5)).toBe(128)
  })

  it('recorta a 0-255 los valores que produce un arrastre fuera del area', () => {
    expect(rgb(-1, 255.6, 1000)).toEqual({ r: 0, g: 255, b: 255 })
  })

  it('rechaza valores no finitos en lugar de propagar NaN al backend', () => {
    expect(() => clampChannel(Number.NaN)).toThrow(RangeError)
    expect(() => clampChannel(Number.POSITIVE_INFINITY)).toThrow(RangeError)
  })
})
