/**
 * Dispositivos en el dominio del cliente.
 *
 * Los tipos del backend se conservan separados a proposito
 * (backend/app/domain/devices/models.py):
 *
 *   - `Device`        identidad registrada + lo que sabe hacer.
 *   - `DeviceLink`    estado efimero del enlace (conectado, rssi, ultimo error).
 *
 *   - `DiscoveredDevice`  resultado de un escaneo: **todavia no existe** en el
 *                         servidor, solo se ha visto por la radio.
 *
 * Colapsarlos fue justo el error que el backend corrigio: la UI pinta cosas
 * distintas con cada uno. Un `DiscoveredDevice` no tiene `id` porque no esta
 * registrado; darle uno invitaria a intentar conectarlo antes de registrarlo.
 */

/**
 * Que sabe hacer el dispositivo conectado.
 *
 * **Es lo unico que decide que controles se habilitan.** Nunca `adapterType`:
 * el tipo de adaptador es una decision de infraestructura y atarle la UI
 * obligaria a tocar componentes cada vez que se soporte hardware nuevo
 * (NEXT_STEPS A7).
 */
export interface DeviceCapabilities {
  readonly rgb: boolean
  readonly brightness: boolean
  readonly effects: boolean
  readonly addressable: boolean
  readonly segments: boolean
  readonly whiteChannel: boolean
  readonly musicMode: boolean
}

/** Nombre de una capacidad. Permite pedir "la capacidad X" sin cadenas sueltas. */
export type CapabilityName = keyof DeviceCapabilities

/** Un dispositivo registrado en el backend. */
export interface Device {
  readonly id: string
  readonly name: string
  /** Familia de hardware. Informativo: NO se usa para decidir la UI. */
  readonly adapterType: string
  readonly address: string | null
  readonly enabled: boolean
  readonly autoConnect: boolean
  readonly connected: boolean
  readonly capabilities: DeviceCapabilities
}

/** Estado del unico enlace que mantiene el proceso backend. */
export interface DeviceLink {
  readonly deviceId: string
  readonly connected: boolean
  readonly rssi: number | null
  /** Ultimo fallo del enlace. Se muestra: un fallo oculto es un fallo repetido. */
  readonly lastError: string | null
}

/**
 * Capacidades de un dispositivo que todavia no conocemos.
 *
 * Todo en `false`: sin dispositivo conectado no hay nada que se pueda hacer, y
 * asumir lo contrario dejaria controles habilitados que fallarian con 409.
 */
export const NO_CAPABILITIES: DeviceCapabilities = {
  rgb: false,
  brightness: false,
  effects: false,
  addressable: false,
  segments: false,
  whiteChannel: false,
  musicMode: false,
}

/**
 * Un dispositivo visto durante un escaneo BLE y **aun no registrado**.
 *
 * `name` es opcional en el anuncio BLE: hay tiras que no publican ninguno. El
 * `rssi` es la unica pista de cercania y por eso se conserva, aunque sea
 * ruidoso; `address` no es portable entre hosts (MAC en Linux, GUID en WinRT),
 * asi que sirve para registrar, no para que el usuario reconozca su tira.
 */
export interface DiscoveredDevice {
  readonly name: string | null
  readonly address: string
  readonly rssi: number | null
}

/**
 * Alta de un dispositivo en el servidor.
 *
 * No lleva `adapterType`: la familia de hardware la decide el backend, que es
 * quien sabe con que adaptador esta corriendo. Elegirla desde la UI seria
 * adivinar. El alta es **idempotente por direccion**: repetirla devuelve el
 * mismo dispositivo, nunca un duplicado ni un 409.
 */
export interface NewDevice {
  readonly name: string | null
  readonly address: string
}
