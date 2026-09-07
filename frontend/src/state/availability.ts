/**
 * Decide si un control esta operativo y, si no lo esta, **por que**.
 *
 * Es una sola funcion y no una condicion repetida en cada componente porque la
 * regla es una sola: **manda `capabilities`, nunca `adapterType`**. Un control
 * deshabilitado sin explicacion es un fallo de accesibilidad y de producto; por
 * eso `reason` no es opcional cuando `enabled` es `false`.
 */
import type { CapabilityName } from '../domain/devices'
import type { LightView } from './lightStateContext'

export interface Availability {
  readonly enabled: boolean
  /** Texto enlazado al control con `aria-describedby`. `null` si esta operativo. */
  readonly reason: string | null
}

const AVAILABLE: Availability = { enabled: true, reason: null }

const CAPABILITY_LABELS: Readonly<Record<CapabilityName, string>> = {
  rgb: 'el color',
  brightness: 'el brillo',
  effects: 'los efectos',
  addressable: 'el direccionamiento por LED',
  segments: 'los segmentos',
  whiteChannel: 'el canal blanco',
  musicMode: 'el modo música',
}

/**
 * @param capability Capacidad exigida por el control, o `null` si solo necesita
 *   que haya un dispositivo conectado (el encendido no es una capacidad: un
 *   dispositivo que no se pueda encender no seria un dispositivo de luz).
 */
export function controlAvailability(
  view: LightView,
  capability: CapabilityName | null,
): Availability {
  if (view.hydration !== 'ready') {
    return { enabled: false, reason: 'Todavía no se conoce el estado del servidor.' }
  }

  if (view.device === null) {
    return { enabled: false, reason: 'No hay ningún dispositivo registrado en el servidor.' }
  }

  if (!view.device.connected) {
    return {
      enabled: false,
      reason: `El dispositivo «${view.device.name}» no está conectado.`,
    }
  }

  if (capability !== null && !view.capabilities[capability]) {
    return {
      enabled: false,
      reason: `El dispositivo conectado no admite ${CAPABILITY_LABELS[capability]}.`,
    }
  }

  return AVAILABLE
}
