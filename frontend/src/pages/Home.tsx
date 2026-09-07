import styles from './Home.module.css'
import { BrightnessSlider } from '../components/BrightnessSlider/BrightnessSlider'
import { ColorPicker } from '../components/ColorPicker/ColorPicker'
import { ColorPresetGrid } from '../components/ColorPresetGrid/ColorPresetGrid'
import { DeviceDiscovery } from '../components/DeviceDiscovery/DeviceDiscovery'
import { DeviceStatus } from '../components/DeviceStatus/DeviceStatus'
import { EffectLibrary } from '../components/EffectLibrary/EffectLibrary'
import { EffectStatusBar } from '../components/EffectStatusBar/EffectStatusBar'
import { PowerToggle } from '../components/PowerToggle/PowerToggle'
import { ProfileLibrary } from '../components/ProfileLibrary/ProfileLibrary'
import { SceneLibrary } from '../components/SceneLibrary/SceneLibrary'
import { SceneQuickBar } from '../components/SceneQuickBar/SceneQuickBar'
import { Alert } from '../components/ui/Alert'
import { Card } from '../components/ui/Card'
import { radioStatus } from '../domain/discovery'
import { effectName } from '../domain/effects'
import { COLOR_PRESETS } from '../domain/presets'
import { useDeviceDiscovery } from '../hooks/useDeviceDiscovery'
import { useEffectCatalog } from '../hooks/useEffectCatalog'
import { useLightControls, useLightState } from '../hooks/useLightState'
import { useProfileCatalog } from '../hooks/useProfileCatalog'
import { useSceneCatalog } from '../hooks/useSceneCatalog'
import { controlAvailability } from '../state/availability'

/**
 * Unica pantalla de la aplicacion (README, Fases 3 a 7).
 *
 * Es **composicion y disposicion**: no hace `fetch`, no guarda estado del
 * servidor y no decide reglas. Toma el modelo de vista ya reconciliado y reparte
 * props; asi cada control se puede probar solo y esta pantalla se lee de un
 * vistazo.
 *
 * ## Disposicion: dos rejillas, no una columna larga
 *
 * Una sola rejilla con `auto-fit`/`minmax` sirve para el movil y para el
 * escritorio: una columna cuando no cabe mas, varias cuando caben, sin arboles
 * separados ni puntos de ruptura escritos a mano.
 *
 * Son **dos** rejillas porque hay dos frecuencias de uso distintas:
 *
 * 1. **Gestion** (arriba): conexion, dispositivos, efectos, escenas y perfiles.
 *    Cada tarjeta es un resumen que se lee —cuantas hay, que esta enlazado— con
 *    un boton que abre su dialogo. Son tareas que se hacen una vez.
 * 2. **Uso diario** (abajo, `margin-top: auto`): el efecto en curso, las escenas
 *    rapidas y los controles manuales. **Nada de esto vive detras de un clic**:
 *    es lo que se toca cada dia y esta a la vista, en el tercio inferior, que es
 *    donde llega el pulgar con el movil en una mano.
 *
 * **Sigue sin router.** Los dialogos no cambian eso: el estado compartido es uno
 * solo y no hay nada que enlazar en profundidad. El dia que haga falta enlace
 * profundo y boton "atras" en la PWA sera el momento; hoy seria infraestructura
 * sin requisito.
 */
export function Home() {
  const view = useLightState()
  const controls = useLightControls()

  // Dar de alta y enlazar son dos pasos del servidor, no uno: el alta la
  // resuelve el hook y el enlace es del estado compartido, que es quien tiene
  // el unico enlace.
  //
  // `system` entra desde el estado compartido en vez de pedirse otra vez: lo
  // miran tambien la tarjeta de conexion y el resumen de dispositivos, y dos
  // lecturas darian dos copias que pueden discrepar.
  const discovery = useDeviceDiscovery({
    onRegistered: controls.connectDevice,
    system: view.system,
  })

  // Los tres catalogos rehidratan el estado global tras una orden aceptada: el
  // estado nuevo llega por el WebSocket, pero ese canal puede estar caido y sin
  // esto el indicador se quedaria mintiendo mientras reconecta.
  //
  // Viven aqui y no dentro de cada dialogo a proposito: el resumen de la
  // tarjeta —cuantos efectos, cuantas escenas— se lee con el dialogo cerrado, y
  // un catalogo que se montara con el modal no tendria nada que contar.
  const effects = useEffectCatalog({ onApplied: controls.refreshState })

  const scenes = useSceneCatalog({
    defaultDeviceId: view.device?.id ?? null,
    effects: effects.state.effects,
    // Una escena de color fijo guarda antes su efecto `STATIC`: el catalogo de
    // efectos tiene que enterarse, y su titular es el otro hook.
    onEffectsChanged: effects.reload,
    onActivated: controls.refreshState,
  })

  const profiles = useProfileCatalog({ onActivated: controls.refreshState })

  const power = controlAvailability(view, null)
  const color = controlAvailability(view, 'rgb')
  const brightness = controlAvailability(view, 'brightness')

  // Reproducir un efecto —y activar una escena o un perfil, que terminan en lo
  // mismo— exige exactamente lo mismo que pintar un color, asi que comparten la
  // disponibilidad en vez de tener tres reglas paralelas.
  const playback = color
  const playbackReason = playback.enabled ? null : playback.reason

  const runningId = view.effect.runningId
  const stoppedId = view.effect.stoppedByCommandId

  return (
    <main className={styles.home}>
      <header className={styles.header}>
        <h1>LED Room</h1>
      </header>

      {/* Arriba del todo y fuera de las rejillas: un fallo no se lee mejor por
          estar dentro de una tarjeta. */}
      {view.notice !== null && (
        <Alert message={view.notice.message} onDismiss={controls.dismissNotice} />
      )}

      <div className={styles.grid}>
        <DeviceStatus
          backend={view.backend}
          realtime={view.realtime}
          device={view.device}
          radio={radioStatus(view.system)}
          linkPending={view.linkPending}
          onConnect={controls.connectDevice}
          onDisconnect={controls.disconnectDevice}
        />

        <DeviceDiscovery
          devices={view.devices}
          discovery={discovery.state}
          linkPending={view.linkPending}
          // El aviso global vive fuera del dialogo, que lo tapa: la tarjeta de
          // dispositivos es la unica cuyas acciones lo alimentan, asi que se lo
          // pasa para poder repetirlo dentro. Es el mismo estado, no otro.
          notice={view.notice?.message ?? null}
          onDismissNotice={controls.dismissNotice}
          onScan={discovery.scan}
          onAdopt={discovery.adopt}
          onConnect={controls.connectDevice}
          onDisconnect={controls.disconnectDevice}
        />

        <EffectLibrary catalog={effects} runningId={runningId} playbackReason={playbackReason} />

        <SceneLibrary
          catalog={scenes}
          effects={effects.state.effects}
          devices={view.devices}
          activeSceneId={view.activeSceneId}
          activationReason={playbackReason}
        />

        <ProfileLibrary
          catalog={profiles}
          scenes={scenes.state.scenes}
          activeSceneId={view.activeSceneId}
          activationReason={playbackReason}
        />
      </div>

      {/* Zona del pulgar: lo que se usa a diario, junto y al final de la
          pagina. `margin-top: auto` la empuja al tercio inferior cuando sobra
          alto, y en el movil queda donde llega la mano sin recolocar nada. */}
      <div className={styles.thumbZone}>
        <EffectStatusBar
          running={
            runningId === null
              ? null
              : { id: runningId, name: effectName(effects.state.effects, runningId) }
          }
          stoppedByCommand={
            stoppedId === null ? null : { name: effectName(effects.state.effects, stoppedId) }
          }
          busy={runningId !== null && effects.state.pendingId === runningId}
          onStop={effects.stop}
        />

        <SceneQuickBar
          catalog={scenes}
          activeSceneId={view.activeSceneId}
          activationReason={playbackReason}
        />

        {/* Los cuatro controles manuales en una tarjeta: son un solo concepto
            —lo que la tira esta haciendo ahora mismo— y el encendido queda al
            final, que es lo mas abajo y lo mas a mano. */}
        <Card title="Luz">
          <ColorPicker
            color={view.light.color}
            disabled={!color.enabled}
            disabledReason={color.reason ?? undefined}
            onPreview={controls.previewColor}
            onCommit={controls.commitColor}
          />

          <ColorPresetGrid
            presets={COLOR_PRESETS}
            current={view.light.color}
            disabled={!color.enabled}
            disabledReason={color.reason ?? undefined}
            onSelect={controls.commitColor}
          />

          <BrightnessSlider
            value={view.light.brightness}
            disabled={!brightness.enabled}
            disabledReason={brightness.reason ?? undefined}
            onChange={controls.setBrightness}
          />

          <PowerToggle
            on={view.light.power}
            disabled={!power.enabled}
            disabledReason={power.reason ?? undefined}
            onChange={controls.setPower}
          />
        </Card>
      </div>
    </main>
  )
}
