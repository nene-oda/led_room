/**
 * Color de dominio del cliente: espejo de `RGBColor` del backend
 * (backend/app/domain/lighting.py).
 *
 * Contrato congelado (ARCHITECTURE.md 3.2), dos representaciones y ninguna mas:
 *
 *   - Cuerpos de mutacion de luz: `{ r, g, b }`, enteros 0-255.
 *   - Estado global y listas de colores: cadena `#RRGGBB` en MAYUSCULAS.
 *
 * Este modulo es la unica frontera entre ambas. Nada de `rgb(...)`, HSV ni
 * tuplas viaja por la API, y ningun componente vuelve a convertir a mano.
 */

/** Color RGB del dominio. Inmutable: se sustituye, no se muta. */
export interface RGBColor {
  readonly r: number
  readonly g: number
  readonly b: number
}

export const CHANNEL_MIN = 0
export const CHANNEL_MAX = 255

const HEX_DIGITS = /^[0-9A-F]{6}$/

/**
 * Normaliza un canal a entero 0-255.
 *
 * Redondeo al entero mas cercano con los medios hacia arriba (`Math.round`:
 * 127.5 -> 128, -0.5 -> 0) y recorte posterior a [0, 255]. Existe porque un
 * selector de color deriva canales de una geometria en coma flotante y podria
 * producir 255.4 o -0.2; el backend rechazaria ese cuerpo con un 422.
 *
 * @throws RangeError si el valor no es finito (NaN, Infinity).
 */
export function clampChannel(value: number): number {
  if (!Number.isFinite(value)) {
    throw new RangeError(`Canal de color invalido: ${String(value)}`)
  }
  return Math.min(CHANNEL_MAX, Math.max(CHANNEL_MIN, Math.round(value)))
}

/** Construye un color valido recortando y redondeando cada canal. */
export function rgb(r: number, g: number, b: number): RGBColor {
  return { r: clampChannel(r), g: clampChannel(g), b: clampChannel(b) }
}

/**
 * Representacion canonica `#RRGGBB` en mayusculas.
 *
 * Las mayusculas no son estetica: `device_state.color_hex` tiene un
 * `CHECK ... GLOB '#[0-9A-F]...'` y el backend guarda con `RGBColor.to_hex()`.
 * Emitir minusculas produciria estados que no coinciden al comparar cadenas.
 * Vale ademas como color CSS, asi que no hace falta un segundo formateador.
 */
export function toHex(color: RGBColor): string {
  return `#${channelToHex(color.r)}${channelToHex(color.g)}${channelToHex(color.b)}`
}

/**
 * Interpreta `#RRGGBB` o `RRGGBB`, con cualquier combinacion de mayusculas y
 * espacios alrededor, igual que `RGBColor.from_hex` del backend.
 *
 * @throws RangeError si la cadena no es un hexadecimal de 6 digitos.
 */
export function fromHex(value: string): RGBColor {
  const digits = value.trim().replace(/^#/, '').toUpperCase()

  if (!HEX_DIGITS.test(digits)) {
    throw new RangeError(`Color hexadecimal invalido: ${JSON.stringify(value)}; se esperaba #RRGGBB`)
  }

  return {
    r: Number.parseInt(digits.slice(0, 2), 16),
    g: Number.parseInt(digits.slice(2, 4), 16),
    b: Number.parseInt(digits.slice(4, 6), 16),
  }
}

function channelToHex(value: number): string {
  return clampChannel(value).toString(16).toUpperCase().padStart(2, '0')
}
