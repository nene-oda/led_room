import { useId, useState } from 'react'

import { RegisteredDeviceList } from './RegisteredDeviceList'
import { ScanProgress } from './ScanProgress'
import { ScanResults } from './ScanResults'
import type { DiscoveredDevice } from '../../domain/devices'
import type { DiscoveryView } from '../../hooks/useDeviceDiscovery'
import { useElapsedSeconds } from '../../hooks/useElapsedSeconds'
import type { RegisteredDevice } from '../../state/lightStateContext'
import { Alert } from '../ui/Alert'
import { Button } from '../ui/Button'
import catalog from '../ui/catalog.module.css'
import { ControlNote } from '../ui/ControlNote'
import { ModalCard } from '../ui/ModalCard'

export interface DeviceDiscoveryProps {
  readonly devices: readonly RegisteredDevice[]
  readonly discovery: DiscoveryView
  readonly linkPending: boolean
  /**
   * Ultimo fallo global sin descartar, si lo hay.
   *
   * Conectar y desconectar se piden desde aqui, pero su fallo va al aviso
   * global, que vive en la pantalla de detras. Un dialogo modal la tapa y
   * `aria-modal` la esconde tambien del lector de pantalla: sin esta copia, el
   * boton se quedaria "trabajando" y luego no pasaria nada visible. Es el mismo
   * aviso, no otro estado: descartarlo aqui lo descarta en los dos sitios.
   */
  readonly notice: string | null
  readonly onDismissNotice: () => void
  readonly onScan: () => void
  readonly onAdopt: (candidate: DiscoveredDevice) => void
  readonly onConnect: (deviceId: string) => void
  readonly onDisconnect: (deviceId: string) => void
}

/**
 * Alta y enlace de dispositivos, dentro de un dialogo.
 *
 * Va **en la pantalla unica** y no en una ruta aparte: no hay router, y añadir
 * uno para una tarea que se hace una vez por tira seria mas infraestructura que
 * producto. La tarjeta, el boton, el dialogo, el foco y Escape los aporta
 * `ModalCard`, que es la misma pieza que usan las otras tres bibliotecas; aqui
 * solo queda el contenido.
 *
 * Lo que se lee sin abrir nada es cuantos dispositivos hay dados de alta; cual
 * esta enlazado lo dice la tarjeta de conexion, que no se esconde detras de
 * ningun clic.
 *
 * **La limitacion se cuenta antes de pulsar.** Cuando el servidor declara que
 * no tiene radio, buscar no se ofrece como si pudiera funcionar: el boton queda
 * deshabilitado con su explicacion enlazada. Descubrirlo pulsando y esperando a
 * una lista vacia es como se llego al problema que esto corrige.
 */
export function DeviceDiscovery({
  devices,
  discovery,
  linkPending,
  notice,
  onDismissNotice,
  onScan,
  onAdopt,
  onConnect,
  onDisconnect,
}: DeviceDiscoveryProps) {
  const [revealAddresses, setRevealAddresses] = useState(false)
  const noRadioId = useId()

  const scanning = discovery.status === 'scanning'
  // El servidor ya dijo que no tiene radio: no es un fallo del que reintentar,
  // es una condicion permanente de este backend.
  const noRadio = discovery.radio === 'missing'
  // `blocked` significa que el servidor ya esta escaneando para otro cliente:
  // reintentar ahora volveria a fallar, asi que el boton espera solo.
  const canScan = !noRadio && !scanning && discovery.status !== 'blocked'
  const elapsed = useElapsedSeconds(scanning)

  const registeredAddresses = new Set(
    devices.map((device) => device.address).filter((address) => address !== null),
  )

  return (
    <ModalCard
      title="Dispositivos"
      summary={summary(devices.length, noRadio)}
      actionText="Gestionar"
      actionLabel="Gestionar dispositivos"
    >
      {notice !== null && <Alert message={notice} onDismiss={onDismissNotice} />}

      <Button
        disabled={!canScan}
        busy={scanning}
        describedBy={noRadio ? noRadioId : undefined}
        onClick={onScan}
      >
        {scanning ? 'Buscando…' : 'Buscar dispositivos'}
      </Button>

      {noRadio ? (
        // Sin region viva ni barra: no hay ningun escaneo que narrar y fingir
        // que se busca algo seria justo la mentira que este panel evita.
        <ControlNote id={noRadioId}>{noRadioExplanation(discovery.adapterType)}</ControlNote>
      ) : (
        <>
          {/* Region viva propia: un escaneo dura segundos y sin anunciarlo la
              pantalla parece colgada, tambien para quien no ve la barra. El
              texto solo cambia al cambiar de fase, no con cada segundo: el
              cronometro va en la barra, que no interrumpe al lector. */}
          <p
            className={catalog.narration ?? ''}
            role="status"
            aria-live="polite"
            aria-label="Estado del escaneo"
          >
            {narrate(discovery, elapsed)}
          </p>

          {scanning && (
            <ScanProgress elapsedSeconds={elapsed} timeoutSeconds={discovery.timeoutSeconds} />
          )}
        </>
      )}

      <ScanResults
        results={discovery.results}
        registeredAddresses={registeredAddresses}
        pendingAddress={discovery.pendingAddress}
        revealAddresses={revealAddresses}
        onAdopt={onAdopt}
      />

      <h3 className={catalog.groupTitle ?? ''}>Dados de alta</h3>
      <RegisteredDeviceList
        devices={devices}
        linkPending={linkPending}
        revealAddresses={revealAddresses}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
      />

      {/* Preferencia de lo que se ve, no un ajuste del dispositivo: por eso
          es un boton de dos estados y no un interruptor. */}
      <Button
        pressed={revealAddresses}
        onClick={() => {
          setRevealAddresses((shown) => !shown)
        }}
      >
        {revealAddresses ? 'Ocultar direcciones' : 'Mostrar direcciones completas'}
      </Button>
    </ModalCard>
  )
}

/** Lo que se lee con el dialogo cerrado. La falta de radio cuenta como estado. */
function summary(count: number, noRadio: boolean): string {
  const registered = count === 1 ? '1 dado de alta' : `${String(count)} dados de alta`
  return noRadio ? `${registered} · servidor sin Bluetooth` : registered
}

/**
 * Que se cuenta del escaneo en cada momento.
 *
 * El hook solo aporta el texto de los fallos, que es donde importa no inventar
 * la causa; los estados normales se redactan aqui, que es donde se ven.
 */
function narrate(discovery: DiscoveryView, elapsedSeconds: number): string {
  if (discovery.message !== null) return discovery.message

  switch (discovery.status) {
    case 'idle':
      return 'Todavía no se ha buscado ningún dispositivo.'
    case 'scanning':
      // Un solo cambio de texto durante el escaneo, y solo si se pasa de la
      // cota: la region es viva y contar los segundos en voz alta seria una
      // interrupcion por segundo.
      return elapsedSeconds >= discovery.timeoutSeconds
        ? 'El escaneo está tardando más de lo que el servidor había previsto, pero sigue en curso.'
        : `Buscando dispositivos por Bluetooth… puede tardar hasta ${String(discovery.timeoutSeconds)} segundos.`
    case 'done':
      return discovery.results.length === 0
        ? nothingFound(discovery.radio === 'available')
        : found(discovery.results.length)
    case 'blocked':
    case 'failed':
      // Con estos dos estados siempre hay `message`; esto solo cierra el tipo.
      return 'No se pudo completar el escaneo.'
  }
}

/**
 * Lista vacia.
 *
 * Con `radio` confirmada, la lista vacia **si** significa que no hay ninguna
 * tira al alcance, y el mensaje puede ser una sola afirmacion con algo que
 * hacer. Sin confirmar —backend sin `GET /system`— vuelve a haber dos causas
 * posibles y se nombran las dos: el 200 vacio del adaptador nulo es idéntico al
 * de una habitacion sin tiras, y elegir una de las dos seria inventarsela.
 */
function nothingFound(radioConfirmed: boolean): string {
  return radioConfirmed
    ? 'El escaneo terminó sin resultados: no hay ninguna tira encendida al alcance. Comprueba que esté enchufada y que no la tenga conectada ya otro móvil o aplicación.'
    : 'El escaneo terminó sin resultados. Puede que no haya ninguna tira encendida cerca, o que el servidor esté usando el adaptador nulo, que no tiene radio Bluetooth y nunca encontrará nada: para descubrir hardware real, el servidor necesita un adaptador con acceso al Bluetooth del equipo.'
}

/**
 * Por que no se puede buscar. Se enseña **antes** de pulsar, no despues.
 *
 * Nombra el adaptador cuando el servidor lo publica: es el dato con el que
 * quien administra el servidor puede arreglarlo, y sin el la explicacion se
 * queda en un "no se puede" sin salida.
 */
function noRadioExplanation(adapterType: string | null): string {
  const adapter = adapterType === null ? 'un adaptador sin radio' : `el adaptador «${adapterType}»`
  return `Este servidor no tiene acceso a Bluetooth: está usando ${adapter}, así que nunca encontrará ninguna tira por mucho que se busque. Para descubrir hardware real hay que ejecutar el backend en un equipo con Bluetooth y arrancarlo con un adaptador con radio (LED_ROOM_DEVICE_ADAPTER). Los dispositivos ya dados de alta se siguen viendo aquí abajo.`
}

function found(count: number): string {
  return count === 1 ? '1 dispositivo encontrado.' : `${String(count)} dispositivos encontrados.`
}
