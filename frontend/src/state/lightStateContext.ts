/**
 * Contrato del unico contexto compartido de la aplicacion.
 *
 * Esta separado del proveedor por dos razones: los componentes solo necesitan
 * los tipos (y `components/**` no puede importar `api/**`), y un fichero `.tsx`
 * que exporta a la vez un componente y valores rompe el refresco rapido de
 * React (`react-refresh/only-export-components`).
 *
 * `LightView` es un **modelo de vista**, no un DTO: solo trae lo que la
 * pantalla pinta, ya reconciliado. Los DTOs del cable se quedan en `api/`.
 */
import { createContext } from 'react'

import type { RGBColor } from '../domain/color'
import type { BackendStatus, RealtimeStatus } from '../domain/connection'
import type { DeviceCapabilities } from '../domain/devices'
import type { LightState } from '../domain/light'
import type { SystemInfo } from '../domain/system'
import type { Notice } from './lightStateReducer'

/**
 * Un dispositivo dado de alta en el servidor, tal y como lo pinta la lista.
 *
 * `connected` no se copia del `Device` que devolvio `GET /devices`: se deriva
 * del enlace vivo, que es lo unico que el WebSocket mantiene al dia. Copiarlo
 * dejaria la lista diciendo "conectado" despues de una desconexion.
 */
export interface RegisteredDevice {
  readonly id: string
  readonly name: string
  /** No portable entre hosts (MAC en Linux, GUID en WinRT). Se enseña enmascarada. */
  readonly address: string | null
  readonly connected: boolean
}

/**
 * El dispositivo con el que trabaja la pantalla, con el detalle del enlace.
 *
 * Extiende `RegisteredDevice` en vez de repetir sus campos: es el mismo
 * dispositivo visto con mas informacion, no otro concepto. `rssi` y `lastError`
 * solo existen mientras hay enlace, por eso no estan en la lista.
 */
export interface DeviceView extends RegisteredDevice {
  readonly rssi: number | null
  readonly lastError: string | null
}

/**
 * Lo que la pantalla necesita saber del efecto en curso.
 *
 * Solo ids: el **catalogo** (nombres, paletas, tipos) no vive aqui. Llega por
 * `GET /effects` y no viaja por el WebSocket, asi que meterlo en el estado
 * compartido crearia una segunda copia que nadie mantendria al dia.
 */
export interface EffectRuntimeView {
  readonly runningId: string | null
  /**
   * Efecto que un comando manual acaba de detener.
   *
   * Se muestra en vez de callarse: el servidor cancela el efecto en curso antes
   * de aplicar cualquier color, brillo o encendido manual, y sin decirlo la
   * pantalla parece apagar el efecto sola.
   */
  readonly stoppedByCommandId: string | null
}

export interface LightView {
  readonly hydration: 'loading' | 'ready' | 'failed'
  /** Señal 1 de 3: el backend responde por HTTP. */
  readonly backend: BackendStatus
  /** Señal 2 de 3: el canal de tiempo real esta abierto. */
  readonly realtime: RealtimeStatus
  /** Señal 3 de 3 (dentro de `device`): el enlace BLE con el dispositivo. */
  readonly device: DeviceView | null
  /** Todos los dispositivos dados de alta, para elegir cual enlazar. */
  readonly devices: readonly RegisteredDevice[]
  /**
   * Lo que el SERVIDOR puede hacer, o `null` mientras no lo haya dicho.
   *
   * Se pide **una vez**, con el resto de la hidratacion, y lo comparten la
   * tarjeta de conexion y la de dispositivos. Es distinto de `capabilities`:
   * eso describe la tira conectada, esto describe si el backend tiene siquiera
   * una radio con la que buscarla.
   */
  readonly system: SystemInfo | null
  readonly light: LightState
  readonly capabilities: DeviceCapabilities
  readonly effect: EffectRuntimeView
  /**
   * Escena que el servidor da por activa, o `null`.
   *
   * Solo el id: el catalogo de escenas llega por `GET /scenes` y no viaja por
   * el WebSocket, asi que subirlo aqui crearia una segunda copia sin dueño.
   * Es lo unico que decide que fila se enseña como activa; pulsar un boton no
   * lo cambia hasta que el servidor lo confirma.
   */
  readonly activeSceneId: string | null
  readonly linkPending: boolean
  readonly notice: Notice | null
}

/**
 * Acciones del usuario.
 *
 * `previewColor` y `commitColor` estan separadas porque van por canales
 * distintos: el arrastre por WebSocket (no persiste) y el cierre del gesto por
 * REST (persiste y cancela el arrastre pendiente en el servidor).
 */
export interface LightControls {
  readonly setPower: (on: boolean) => void
  readonly previewColor: (color: RGBColor) => void
  readonly commitColor: (color: RGBColor) => void
  readonly setBrightness: (value: number) => void
  /**
   * Enlaza un dispositivo concreto.
   *
   * Recibe el id en vez de operar sobre "el activo" porque desde la lista se
   * puede pedir cualquiera, y porque asi la accion no depende de estado oculto:
   * su identidad es estable entre renders sin necesidad de una ref.
   */
  readonly connectDevice: (deviceId: string) => void
  readonly disconnectDevice: (deviceId: string) => void
  /**
   * Vuelve a pedir el estado global al servidor.
   *
   * Lo usan las acciones que lo cambian **por REST** y cuya confirmacion viaja
   * por el WebSocket: si el socket esta reconectando, sin esto el indicador se
   * quedaria describiendo lo de antes. Un frame mas nuevo que ya haya llegado
   * gana igualmente, porque la rehidratacion se filtra por `version`.
   */
  readonly refreshState: () => void
  readonly dismissNotice: () => void
}

export interface LightContextValue {
  readonly view: LightView
  readonly controls: LightControls
}

export const LightStateContext = createContext<LightContextValue | null>(null)
