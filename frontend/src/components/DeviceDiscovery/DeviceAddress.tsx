import styles from './DeviceDiscovery.module.css'
import { maskAddress } from '../../domain/discovery'

export interface DeviceAddressProps {
  readonly address: string | null
  /** El usuario ha pedido verla entera. Por defecto se muestra recortada. */
  readonly revealed: boolean
}

/**
 * Direccion de un dispositivo, recortada salvo que se pida verla.
 *
 * Se muestra en segundo plano y a proposito no es el dato principal: no es
 * portable entre hosts (una MAC en Linux, un GUID en Windows) y el usuario no
 * reconoce su tira por ella, sino por el nombre y la cercania. Va recortada por
 * defecto para que una captura de pantalla de esta lista no la lleve entera.
 */
export function DeviceAddress({ address, revealed }: DeviceAddressProps) {
  if (address === null) {
    return <span className={styles.address ?? ''}>Sin dirección</span>
  }

  return (
    <span className={styles.address ?? ''}>{revealed ? address : maskAddress(address)}</span>
  )
}
