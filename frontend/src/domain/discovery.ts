/**
 * Reglas del descubrimiento de dispositivos. **Puras**: ni React, ni red.
 *
 * Concentra las decisiones que la UI repetiria de otro modo en cada
 * componente: si se puede escanear siquiera, cuanto dura un escaneo, como se
 * lee un RSSI y cuanto de una direccion se enseña.
 */
import type { DiscoveredDevice } from './devices'
import type { SystemInfo } from './system'

/**
 * Duracion de un escaneo, en segundos, **cuando el servidor no la ha dicho**.
 *
 * Es un respaldo, no la verdad: la cifra buena es `scanTimeoutSeconds` de
 * `GET /system`, que es la unica que conoce `LED_ROOM_BLE_SCAN_TIMEOUT`. Se usa
 * mientras esa respuesta no esta disponible (backend anterior al endpoint, o
 * hidratacion todavia en curso) para no dejar la UI sin ninguna cota con la que
 * dibujar progreso.
 */
export const SCAN_TIMEOUT_SECONDS = 10

/**
 * Tiempo minimo que el indicador de escaneo permanece visible, en ms.
 *
 * Un servidor que contesta en 5 ms hace que el progreso aparezca y desaparezca
 * en el mismo fotograma: lo que se percibe no es «ha buscado y no hay nada»,
 * sino «el panel ha parpadeado». Mantenerlo un instante convierte ese parpadeo
 * en un paso legible.
 *
 * **No es un retardo cosmetico aplicado a ciegas**: solo cubre una espera que
 * de verdad ocurrio. Cuando ya se sabe que el servidor no tiene radio no se
 * escanea en absoluto, asi que este minimo no llega a aplicarse; fingir una
 * busqueda que no existe seria mentir, no pulir.
 */
export const MIN_VISIBLE_SCAN_MS = 400

/**
 * Si el servidor puede buscar dispositivos por radio.
 *
 * Tres estados y no un booleano: **«todavia no lo ha dicho» no es «no puede»**.
 * Mientras `GET /system` no conteste —o si el backend es anterior a ese
 * endpoint— la UI no puede afirmar ninguna de las dos cosas, y deshabilitar el
 * boton por no saber seria tan falso como prometer resultados.
 */
export type RadioStatus = 'unknown' | 'available' | 'missing'

export function radioStatus(system: SystemInfo | null): RadioStatus {
  if (system === null) return 'unknown'
  return system.supportsDiscovery ? 'available' : 'missing'
}

/** Cota del escaneo: la del servidor si la publica, el respaldo si no. */
export function scanTimeoutOf(system: SystemInfo | null): number {
  return system?.scanTimeoutSeconds ?? SCAN_TIMEOUT_SECONDS
}

/**
 * Cercania estimada a partir del RSSI.
 *
 * El RSSI es ruidoso y depende de la antena, del cuerpo que se interponga y de
 * la orientacion: sirve para **ordenar** candidatos y para distinguir "la tira
 * de esta habitacion" de "la del vecino", no para medir metros. Por eso hay
 * tres tramos anchos y no un numero disfrazado de distancia.
 */
export type SignalStrength = 'near' | 'medium' | 'far' | 'unknown'

const NEAR_DBM = -60
const MEDIUM_DBM = -75

export function signalStrength(rssi: number | null): SignalStrength {
  if (rssi === null || !Number.isFinite(rssi)) return 'unknown'
  if (rssi >= NEAR_DBM) return 'near'
  if (rssi >= MEDIUM_DBM) return 'medium'
  return 'far'
}

/**
 * Ordena de mas cerca a mas lejos, y deja al final los que no publican RSSI.
 *
 * Es lo que convierte una lista de anuncios en una lista util: la tira que
 * tienes delante suele ser la primera. Devuelve una copia; la entrada no se
 * toca.
 */
export function sortByProximity(devices: readonly DiscoveredDevice[]): DiscoveredDevice[] {
  return [...devices].sort((a, b) => (b.rssi ?? -Infinity) - (a.rssi ?? -Infinity))
}

/**
 * Version corta de una direccion, pensada para que no se lea entera de un
 * vistazo ni en una captura de pantalla compartida.
 *
 * No es seguridad de verdad —la direccion viaja por la red local y esta a un
 * clic de distancia—, sino higiene: en Windows/WinRT es un GUID y en Linux una
 * MAC, ninguno de los dos identifica nada para el usuario, que se guia por el
 * nombre y el RSSI. Las direcciones cortas se dejan tal cual: recortarlas no
 * ocultaria nada y solo quitaria la unica pista que hay.
 */
const MIN_MASKABLE = 8
const KEEP = 4

export function maskAddress(address: string): string {
  const value = address.trim()
  if (value.length <= MIN_MASKABLE) return value
  return `${value.slice(0, KEEP)}…${value.slice(-KEEP)}`
}
