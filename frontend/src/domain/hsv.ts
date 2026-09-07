/**
 * Conversion HSV <-> RGB. **Solo para la interfaz.**
 *
 * Ni un byte de HSV viaja por la API: el contrato son `{r,g,b}` y `#RRGGBB`
 * (ARCHITECTURE.md 3.2). Existe porque un selector de color bidimensional se
 * navega en tono y saturacion, no en tres canales independientes: arrastrar
 * sobre un plano R/G es incomprensible para una persona.
 *
 * `v` (valor) se mantiene separado del **brillo** del dispositivo: el brillo es
 * un canal propio del hardware con su propio control. Mezclarlos haria que
 * bajar el brillo cambiase el color enviado.
 */
import { clampChannel, rgb, type RGBColor } from './color'

export interface HSVColor {
  /** Tono en grados, 0-360 (360 se normaliza a 0). */
  readonly h: number
  /** Saturacion 0-1. */
  readonly s: number
  /** Valor 0-1. */
  readonly v: number
}

export const HUE_MAX = 360

/** Normaliza el tono al rango [0, 360). */
export function normalizeHue(hue: number): number {
  if (!Number.isFinite(hue)) {
    throw new RangeError(`Tono invalido: ${String(hue)}`)
  }
  return ((hue % HUE_MAX) + HUE_MAX) % HUE_MAX
}

function unit(value: number): number {
  if (!Number.isFinite(value)) {
    throw new RangeError(`Valor invalido: ${String(value)}`)
  }
  return Math.min(1, Math.max(0, value))
}

/** HSV -> RGB. Los canales salen ya recortados y redondeados a 0-255. */
export function hsvToRgb({ h, s, v }: HSVColor): RGBColor {
  const hue = normalizeHue(h) / 60
  const saturation = unit(s)
  const value = unit(v)

  const chroma = value * saturation
  const second = chroma * (1 - Math.abs((hue % 2) - 1))
  const offset = value - chroma

  const [r, g, b] = sector(Math.floor(hue) % 6, chroma, second)
  return rgb((r + offset) * 255, (g + offset) * 255, (b + offset) * 255)
}

function sector(index: number, chroma: number, second: number): [number, number, number] {
  switch (index) {
    case 0:
      return [chroma, second, 0]
    case 1:
      return [second, chroma, 0]
    case 2:
      return [0, chroma, second]
    case 3:
      return [0, second, chroma]
    case 4:
      return [second, 0, chroma]
    default:
      return [chroma, 0, second]
  }
}

/**
 * RGB -> HSV. Sirve para colocar el puntero del selector sobre el color que el
 * servidor dice que esta aplicado.
 *
 * Con un gris (saturacion 0) el tono es indeterminado y se devuelve 0: es la
 * convencion habitual y evita que el puntero salte al azar.
 */
export function rgbToHsv(color: RGBColor): HSVColor {
  const r = clampChannel(color.r) / 255
  const g = clampChannel(color.g) / 255
  const b = clampChannel(color.b) / 255

  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const chroma = max - min

  return { h: hueOf(r, g, b, max, chroma), s: max === 0 ? 0 : chroma / max, v: max }
}

function hueOf(r: number, g: number, b: number, max: number, chroma: number): number {
  if (chroma === 0) return 0
  if (max === r) return normalizeHue(60 * ((g - b) / chroma))
  if (max === g) return normalizeHue(60 * ((b - r) / chroma + 2))
  return normalizeHue(60 * ((r - g) / chroma + 4))
}
