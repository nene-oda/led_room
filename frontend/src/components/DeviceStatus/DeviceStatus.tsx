import styles from './DeviceStatus.module.css'
import type { BackendStatus, RealtimeStatus } from '../../domain/connection'
import type { RadioStatus } from '../../domain/discovery'
import type { DeviceView } from '../../state/lightStateContext'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export interface DeviceStatusProps {
  /** Señal 1: ¿responde el backend por HTTP? */
  readonly backend: BackendStatus
  /** Señal 2: ¿esta abierto el canal de tiempo real? */
  readonly realtime: RealtimeStatus
  /** Señal 3: ¿esta el backend enlazado con el dispositivo? */
  readonly device: DeviceView | null
  /**
   * Si el servidor tiene radio, segun el propio servidor.
   *
   * Solo matiza la tercera señal: "no hay ningun dispositivo" se lee muy
   * distinto segun el servidor pueda buscarlos o no. La explicacion completa y
   * la salida viven en la tarjeta de dispositivos; aqui basta el hecho.
   */
  readonly radio: RadioStatus
  readonly linkPending: boolean
  /**
   * Reciben el id del dispositivo que se ve aqui.
   *
   * El componente ya lo tiene y devolverlo evita que el llamante monte un cierre
   * por render para recordarselo, ademas de dejar la accion valida cuando hay
   * mas de un dispositivo dado de alta.
   */
  readonly onConnect: (deviceId: string) => void
  readonly onDisconnect: (deviceId: string) => void
}

type Tone = 'ok' | 'warn' | 'error' | 'idle'

interface Signal {
  readonly label: string
  readonly text: string
  readonly tone: Tone
}

/**
 * Las **tres** señales de conexion, cada una por separado.
 *
 * Nunca se colapsan en un punto verde. Son tres fallos distintos con tres
 * soluciones distintas —el servidor caido, el socket caido y la tira fuera de
 * alcance—, y un unico indicador obligaria a adivinar cual de los tres es.
 * Ademas, "WebSocket abierto" no implica "dispositivo conectado": ese es
 * justamente el caso en el que los controles se deshabilitan con explicacion.
 *
 * Es una tarjeta mas de la rejilla, pero **sin dialogo**: el estado se mira,
 * no se gestiona, y esconderlo detras de un clic seria justo lo contrario de lo
 * que hace falta cuando algo se cae.
 */
export function DeviceStatus({
  backend,
  realtime,
  device,
  radio,
  linkPending,
  onConnect,
  onDisconnect,
}: DeviceStatusProps) {
  const signals: readonly Signal[] = [
    backendSignal(backend),
    realtimeSignal(realtime),
    deviceSignal(device, radio),
  ]

  return (
    <Card title="Conexión">
      {/* Una sola region viva para las tres: anunciarlas por separado
          convertiria una reconexion en tres interrupciones seguidas. */}
      <ul className={styles.signals} role="status" aria-live="polite">
        {signals.map((signal) => (
          <li key={signal.label} className={styles.signal}>
            <span
              className={`${styles.dot ?? ''} ${styles[signal.tone] ?? ''}`}
              aria-hidden="true"
            />
            <span className={styles.label}>{signal.label}</span>
            <span className={styles.text}>{signal.text}</span>
          </li>
        ))}
      </ul>

      {device !== null && (
        <Button
          busy={linkPending}
          onClick={() => {
            const act = device.connected ? onDisconnect : onConnect
            act(device.id)
          }}
        >
          {linkPending ? 'Trabajando…' : device.connected ? 'Desconectar' : 'Conectar'}
        </Button>
      )}

      {device?.lastError != null && (
        <p className={styles.lastError}>Último fallo del enlace: {device.lastError}</p>
      )}
    </Card>
  )
}

function backendSignal(backend: BackendStatus): Signal {
  switch (backend) {
    case 'checking':
      return { label: 'Servidor', text: 'Comprobando…', tone: 'idle' }
    case 'reachable':
      return { label: 'Servidor', text: 'Responde', tone: 'ok' }
    case 'unreachable':
      return { label: 'Servidor', text: 'Sin respuesta', tone: 'error' }
  }
}

function realtimeSignal(realtime: RealtimeStatus): Signal {
  switch (realtime) {
    case 'connecting':
      return { label: 'Tiempo real', text: 'Conectando…', tone: 'idle' }
    case 'open':
      return { label: 'Tiempo real', text: 'Conectado', tone: 'ok' }
    case 'reconnecting':
      // Visible a proposito: un reintento silencioso deja al usuario creyendo
      // que ve el estado actual cuando lleva minutos congelado.
      return { label: 'Tiempo real', text: 'Reconectando…', tone: 'warn' }
    case 'closed':
      return { label: 'Tiempo real', text: 'Cerrado', tone: 'error' }
  }
}

function deviceSignal(device: DeviceView | null, radio: RadioStatus): Signal {
  if (device === null) {
    // Sin radio, "ninguno registrado" no invita a buscar: no se puede. Decirlo
    // aqui evita el viaje de ida y vuelta al dialogo para descubrirlo.
    return {
      label: 'Dispositivo',
      text:
        radio === 'missing'
          ? 'Ninguno registrado · el servidor no tiene Bluetooth'
          : 'Ninguno registrado',
      tone: 'error',
    }
  }
  return device.connected
    ? { label: 'Dispositivo', text: `${device.name} · conectado`, tone: 'ok' }
    : { label: 'Dispositivo', text: `${device.name} · desconectado`, tone: 'error' }
}
