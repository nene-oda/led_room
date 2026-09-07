/**
 * Colores predefinidos.
 *
 * **NO son escenas.** Son constantes del cliente: no existen en el backend, no
 * se persisten, no tienen `id` y no hay ningun endpoint detras. Pulsar uno
 * equivale exactamente a mover el selector hasta ese color, ni mas ni menos.
 *
 * Se documenta aqui porque la confusion es facil y cara: cuando llegue la Fase
 * 6, las escenas seran entidades del servidor (`POST /scenes/{id}/activate`) y
 * nadie debe intentar "migrar" esta lista.
 *
 * Los nombres son la etiqueta accesible del boton, asi que se leen en voz alta:
 * "Cálido", no "#FFB46E".
 */
import { rgb, type RGBColor } from './color'

export interface ColorPreset {
  readonly name: string
  readonly color: RGBColor
}

export const COLOR_PRESETS: readonly ColorPreset[] = [
  { name: 'Blanco cálido', color: rgb(255, 180, 110) },
  { name: 'Blanco frío', color: rgb(255, 255, 255) },
  { name: 'Rojo', color: rgb(255, 0, 0) },
  { name: 'Ámbar', color: rgb(255, 140, 0) },
  { name: 'Verde', color: rgb(0, 200, 60) },
  { name: 'Cian', color: rgb(0, 200, 255) },
  { name: 'Azul', color: rgb(0, 60, 255) },
  { name: 'Violeta', color: rgb(123, 0, 255) },
]
