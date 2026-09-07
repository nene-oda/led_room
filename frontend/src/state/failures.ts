/**
 * Traduccion de un fallo de red o de API a algo que se le puede enseñar a una
 * persona, y a la señal de "backend alcanzable".
 *
 * La distincion importa y por eso vive en un solo sitio: un `ApiError` **prueba
 * que el servidor contesto** (aunque sea para decir que no), mientras que un
 * fallo de `fetch` significa que no hay backend al otro lado. Colapsar ambos
 * dejaria al usuario reiniciando el router cuando lo que pasa es que la tira
 * esta fuera de alcance.
 */
import { ApiError } from '../api/client'
import { describeErrorCode, type ErrorCode } from '../domain/errors'

export interface Failure {
  readonly message: string
  readonly backendReachable: boolean
}

/**
 * Operacion durante la que fallo, cuando el codigo por si solo es ambiguo.
 *
 * `device_busy` es el caso que obliga a esto: el mismo codigo significa "ya hay
 * un escaneo en curso" en `GET /devices/scan` y "ya hay otro dispositivo
 * enlazado" en `POST /devices/{id}/connect`. Con un unico texto, uno de los dos
 * mentiria. El catalogo de `domain/errors.ts` sigue siendo la base; esto solo
 * lo afina donde el contexto aporta algo cierto.
 */
export type FailureContext =
  | 'scan'
  | 'link'
  | 'effect'
  | 'scene'
  | 'scene-activation'
  | 'profile'
  | 'profile-activation'

/**
 * Lo que puede salir mal al ACTIVAR, contado sin suavizarlo.
 *
 * Los tres codigos comparten una misma verdad y por eso los tres la dicen:
 * **el servidor valida todos los objetivos antes de escribir en el
 * dispositivo**, asi que un 409 significa que no se reprodujo nada. Decir "se
 * activó parcialmente" seria describir un estado que el backend no permite.
 */
const ACTIVATION_MESSAGES: Partial<Record<ErrorCode, string>> = {
  device_not_connected:
    'No se activó nada: alguno de sus dispositivos no es el que está conectado. Una escena se activa entera o no se activa.',
  unsupported_capability:
    'No se activó nada: al dispositivo conectado le falta alguna capacidad que hace falta. Una escena se activa entera o no se activa.',
  invalid_payload:
    'No se activó nada: alguno de sus efectos no tiene los pasos que su algoritmo necesita. Edítalo en la biblioteca de efectos y vuelve a intentarlo.',
  nothing_to_activate:
    'La escena no tiene ningún dispositivo habilitado que reproducir: edítala y añádele uno.',
}

const CONTEXT_MESSAGES: Readonly<Record<FailureContext, Partial<Record<ErrorCode, string>>>> = {
  scan: {
    device_busy: 'Ya hay un escaneo en curso. Espera a que termine para lanzar otro.',
    // `device_unavailable` (503) no necesita texto propio aqui: el catalogo
    // general ya dice exactamente lo que pasa, porque el backend separo el caso
    // "este host no tiene Bluetooth utilizable" del fallo de escaneo.
    //
    // Lo que queda en 502 es un fallo del escaneo CON radio presente, o una
    // expiracion. El backend todavia no los distingue entre si.
    device_write_failed:
      'El servidor no pudo completar el escaneo: puede que la operación expirara o que fallara el adaptador Bluetooth.',
  },
  link: {
    device_busy:
      'Solo puede haber un dispositivo enlazado a la vez. Desconecta el que está conectado y vuelve a intentarlo.',
  },
  effect: {
    // Al guardar significa que la definicion no es valida; al reproducir, que
    // el efecto no tiene los pasos que su algoritmo necesita. Es la misma
    // causa contada donde el usuario puede corregirla.
    invalid_payload: 'El servidor rechazó el efecto: revisa el tipo, la paleta y los tiempos.',
    unsupported_capability:
      'El dispositivo conectado no puede reproducir este efecto: le falta alguna capacidad que el efecto necesita.',
  },
  scene: {
    invalid_payload:
      'El servidor rechazó la escena: revisa el nombre y que cada dispositivo aparezca una sola vez.',
  },
  'scene-activation': ACTIVATION_MESSAGES,
  profile: {
    invalid_payload:
      'El servidor rechazó el perfil: revisa el nombre y que cada escena aparezca una sola vez.',
  },
  // Activar un perfil ES activar su escena predeterminada, asi que hereda sus
  // mensajes en vez de tener una copia que se desincronizaria. Lo unico propio
  // es el perfil sin escenas, que comparte codigo con la escena sin objetivos.
  'profile-activation': {
    ...ACTIVATION_MESSAGES,
    nothing_to_activate:
      'El perfil no tiene ninguna escena que activar: edítalo y añádele al menos una.',
  },
}

export function describeFailure(error: unknown, context?: FailureContext): Failure {
  if (error instanceof ApiError) {
    return { message: describeApiError(error, context), backendReachable: true }
  }

  return { message: 'No se pudo contactar con el servidor.', backendReachable: false }
}

function describeApiError(error: ApiError, context: FailureContext | undefined): string {
  if (error.code === null) {
    return `El servidor rechazó la petición (HTTP ${String(error.status)}).`
  }
  const contextual = context === undefined ? undefined : CONTEXT_MESSAGES[context][error.code]
  return contextual ?? describeErrorCode(error.code)
}
