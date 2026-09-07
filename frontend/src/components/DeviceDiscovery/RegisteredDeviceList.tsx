import { DeviceAddress } from './DeviceAddress'
import type { RegisteredDevice } from '../../state/lightStateContext'
import styles from '../ui/catalog.module.css'
import { Button } from '../ui/Button'

export interface RegisteredDeviceListProps {
  readonly devices: readonly RegisteredDevice[]
  /** Hay una operacion de enlace en curso: no se encadenan dos. */
  readonly linkPending: boolean
  readonly revealAddresses: boolean
  readonly onConnect: (deviceId: string) => void
  readonly onDisconnect: (deviceId: string) => void
}

/**
 * Dispositivos dados de alta en el servidor.
 *
 * Solo uno puede estar enlazado a la vez, asi que la lista no es un selector
 * multiple: cada fila ofrece conectar o desconectar **ese** dispositivo y el
 * servidor decide. Cuando rechaza por tener otro enlazado, el aviso de la
 * pantalla lo explica y aqui esta el boton para desconectar el actual.
 */
export function RegisteredDeviceList({
  devices,
  linkPending,
  revealAddresses,
  onConnect,
  onDisconnect,
}: RegisteredDeviceListProps) {
  if (devices.length === 0) {
    return (
      <p className={styles.empty ?? ''}>
        No hay ningún dispositivo dado de alta. Busca uno con el botón de arriba.
      </p>
    )
  }

  return (
    <ul className={styles.list ?? ''}>
      {devices.map((device) => (
        <li key={device.id} className={styles.row ?? ''}>
          <span className={styles.rowMain ?? ''}>
            <span className={styles.name ?? ''}>{device.name}</span>
            <span className={styles.meta ?? ''}>
              <DeviceAddress address={device.address} revealed={revealAddresses} />
              {/* "Enlazado", no "conectado": aqui la pregunta no es si el
                  dispositivo responde, sino cual de los dados de alta ocupa el
                  unico enlace, que es justo lo que rechaza un 409. */}
              <span>{device.connected ? 'Enlazado' : 'Sin enlazar'}</span>
            </span>
          </span>

          <Button
            busy={linkPending}
            ariaLabel={`${device.connected ? 'Desconectar' : 'Conectar'} ${device.name}`}
            onClick={() => {
              const act = device.connected ? onDisconnect : onConnect
              act(device.id)
            }}
          >
            {device.connected ? 'Desconectar' : 'Conectar'}
          </Button>
        </li>
      ))}
    </ul>
  )
}
