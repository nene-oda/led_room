/**
 * Codigos de error del backend y su traduccion a lenguaje humano.
 *
 * El catalogo lo fija `ErrorCode` en backend/app/application/errors.py y es
 * contrato: **la UI decide que mensaje mostrar a partir del codigo, jamas
 * parseando el texto**, que puede cambiar sin previo aviso.
 *
 * Vive en `domain/` porque lo consumen tanto `api/` (que lo extrae del cuerpo
 * `{"detail": {"code", "message"}}`) como la capa de estado (que lo convierte
 * en un aviso visible). `components/**` no importa `api/**`.
 */

export const ERROR_CODES = [
  'device_not_found',
  'effect_not_found',
  'scene_not_found',
  'profile_not_found',
  'nothing_to_activate',
  'device_not_connected',
  'unsupported_capability',
  'device_busy',
  'device_unavailable',
  'invalid_payload',
  'device_write_failed',
  'internal_error',
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

export function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === 'string' && (ERROR_CODES as readonly string[]).includes(value)
}

const MESSAGES: Readonly<Record<ErrorCode, string>> = {
  device_not_found: 'El dispositivo ya no está registrado en el servidor.',
  effect_not_found: 'El efecto ya no está guardado en el servidor.',
  scene_not_found: 'La escena ya no está guardada en el servidor.',
  profile_not_found: 'El perfil ya no está guardado en el servidor.',
  nothing_to_activate: 'No hay nada que activar: todavía está sin terminar de configurar.',
  device_not_connected: 'No hay ningún dispositivo conectado.',
  unsupported_capability: 'El dispositivo conectado no admite esa función.',
  device_busy: 'Hay otro dispositivo ocupando el enlace.',
  device_unavailable:
    'El servidor no puede usar el Bluetooth: comprueba que el equipo tenga adaptador, que esté encendido y que el sistema le dé permiso.',
  invalid_payload: 'El servidor rechazó el valor enviado.',
  device_write_failed: 'No se pudo escribir en el dispositivo.',
  internal_error: 'Error interno del servidor.',
}

/**
 * Mensaje estable para el usuario.
 *
 * Deliberadamente NO cae en el texto del servidor: ese texto esta pensado para
 * un log y en los 500 es generico por diseño.
 */
export function describeErrorCode(code: ErrorCode): string {
  return MESSAGES[code]
}
