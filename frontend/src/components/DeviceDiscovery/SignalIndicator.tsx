import styles from './DeviceDiscovery.module.css'
import { signalStrength, type SignalStrength } from '../../domain/discovery'

/**
 * Cercania de un anuncio BLE, en palabras antes que en numeros.
 *
 * El RSSI crudo no le dice nada a nadie, pero es la unica forma de distinguir
 * la tira que tienes delante de la del vecino, asi que se muestra **traducido**
 * y con el valor detras para quien sepa leerlo. Las barras son decorativas: el
 * texto es lo que anuncia un lector de pantalla, porque el color y la forma por
 * si solos no son una señal accesible.
 */
const LABELS: Readonly<Record<SignalStrength, string>> = {
  near: 'Cerca',
  medium: 'Alcance medio',
  far: 'Lejos',
  unknown: 'Sin medida',
}

const BARS: Readonly<Record<SignalStrength, number>> = {
  near: 3,
  medium: 2,
  far: 1,
  unknown: 0,
}

export function SignalIndicator({ rssi }: { readonly rssi: number | null }) {
  const strength = signalStrength(rssi)
  const filled = BARS[strength]

  return (
    <span className={styles.signal ?? ''}>
      <span className={styles.bars ?? ''} aria-hidden="true">
        {[1, 2, 3].map((level) => (
          <span
            key={level}
            className={`${styles.bar ?? ''} ${level <= filled ? (styles.on ?? '') : ''}`}
          />
        ))}
      </span>
      <span>
        {LABELS[strength]}
        {rssi !== null && <span className={styles.rssi ?? ''}> · {rssi} dBm</span>}
      </span>
    </span>
  )
}
