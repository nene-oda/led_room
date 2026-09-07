/**
 * Estado de la luz en el dominio del cliente.
 *
 * Espejo de `LightState` del backend (backend/app/domain/lighting.py) con dos
 * diferencias deliberadas y ninguna mas:
 *
 *   - `color` es `RGBColor`, no la cadena `#RRGGBB`. La cadena es una forma del
 *     cable; la conversion vive en `api/dto.ts` y no se repite en la UI.
 *   - Las claves van en camelCase, como el resto del dominio del cliente.
 *
 * El brillo es un entero 0-100 (ARCHITECTURE.md 3.3). La escala del hardware es
 * asunto exclusivo del adaptador del backend: aqui nunca aparece 0-255.
 */
import type { RGBColor } from './color'

export const BRIGHTNESS_MIN = 0
export const BRIGHTNESS_MAX = 100

/** Estado deseado de la tira. Inmutable: se sustituye, no se muta. */
export interface LightState {
  readonly power: boolean
  readonly color: RGBColor
  readonly brightness: number
}

/**
 * Normaliza el brillo a entero 0-100.
 *
 * Existe por el mismo motivo que `clampChannel`: un slider puede producir
 * valores fuera de rango o con decimales y el backend los rechazaria con 422.
 *
 * @throws RangeError si el valor no es finito.
 */
export function clampBrightness(value: number): number {
  if (!Number.isFinite(value)) {
    throw new RangeError(`Brillo invalido: ${String(value)}`)
  }
  return Math.min(BRIGHTNESS_MAX, Math.max(BRIGHTNESS_MIN, Math.round(value)))
}
