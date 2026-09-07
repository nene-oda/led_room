import { DeviceAddress } from './DeviceAddress'
import { SignalIndicator } from './SignalIndicator'
import styles from '../ui/catalog.module.css'
import type { DiscoveredDevice } from '../../domain/devices'
import { Button } from '../ui/Button'

export interface ScanResultsProps {
  readonly results: readonly DiscoveredDevice[]
  /** Direcciones ya dadas de alta: evita ofrecer dos veces la misma tira. */
  readonly registeredAddresses: ReadonlySet<string>
  readonly pendingAddress: string | null
  readonly revealAddresses: boolean
  readonly onAdopt: (candidate: DiscoveredDevice) => void
}

const UNNAMED = 'Sin nombre'

/**
 * Lo que se vio en el ultimo escaneo, de mas cerca a mas lejos.
 *
 * Un resultado **no es** un dispositivo: no existe en el servidor hasta que se
 * da de alta, por eso la accion es "Registrar y conectar" y no "Conectar". Se
 * ordenan por cercania porque el nombre suele repetirse entre tiras del mismo
 * modelo y la unica forma practica de acertar con la tuya es que sea la que
 * mejor señal tiene.
 */
export function ScanResults({
  results,
  registeredAddresses,
  pendingAddress,
  revealAddresses,
  onAdopt,
}: ScanResultsProps) {
  if (results.length === 0) return null

  return (
    <ul className={styles.list ?? ''}>
      {results.map((candidate) => {
        const known = registeredAddresses.has(candidate.address)
        const name = candidate.name ?? UNNAMED

        return (
          <li key={candidate.address} className={styles.row ?? ''}>
            <span className={styles.rowMain ?? ''}>
              <span className={styles.name ?? ''}>{name}</span>
              <span className={styles.meta ?? ''}>
                <DeviceAddress address={candidate.address} revealed={revealAddresses} />
                <SignalIndicator rssi={candidate.rssi} />
              </span>
            </span>

            <Button
              disabled={known}
              busy={pendingAddress === candidate.address}
              ariaLabel={known ? `${name} ya está dado de alta` : `Registrar y conectar ${name}`}
              onClick={() => {
                onAdopt(candidate)
              }}
            >
              {known ? 'Ya está en la lista' : 'Registrar y conectar'}
            </Button>
          </li>
        )
      })}
    </ul>
  )
}
