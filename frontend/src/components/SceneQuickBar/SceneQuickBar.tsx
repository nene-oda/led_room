import { useId } from 'react'

import styles from './SceneQuickBar.module.css'
import { favoriteScenes, sceneName } from '../../domain/scenes'
import type { SceneCatalog } from '../../hooks/useSceneCatalog'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { ControlNote } from '../ui/ControlNote'

export interface SceneQuickBarProps {
  /**
   * Catalogo y acciones, tal y como los expone `useSceneCatalog`.
   *
   * Se pasa entero, igual que en la biblioteca de efectos: es un solo concepto
   * y desmontarlo en seis props solo produciria una lista de reenvios.
   */
  readonly catalog: SceneCatalog
  /** Escena que el SERVIDOR da por activa. Nunca una suposicion del cliente. */
  readonly activeSceneId: string | null
  /** Por que no se puede activar nada ahora mismo. `null` = se puede. */
  readonly activationReason: string | null
}

/**
 * Las escenas favoritas, a un toque y fuera de cualquier dialogo.
 *
 * El README 27 pone "QUICK SCENES" en la pantalla principal, y con razon:
 * activar es lo que se hace a diario y editar lo que se hace una vez. Meterlas
 * en el dialogo de escenas costaria dos toques y una busqueda visual cada
 * vez.
 *
 * Es la **unica region viva de las escenas**: aqui se anuncia cual esta activa y
 * aqui aparece el fallo de una activacion, aunque se haya pedido desde la
 * lista completa. La lista tiene su propia narracion para el catalogo (cargar,
 * guardar, borrar), que es otra cosa y no debe sonar dos veces.
 *
 * El resaltado sale de `activeSceneId`, que viene del estado global: pulsar no
 * lo cambia. Un indicador optimista aqui seria especialmente dañino, porque el
 * servidor rechaza la escena ENTERA si algo no encaja y la tira se quedaria
 * como estaba mientras la pantalla dice que cambio.
 */
export function SceneQuickBar({ catalog, activeSceneId, activationReason }: SceneQuickBarProps) {
  const reasonId = useId()
  const { state } = catalog
  const favorites = favoriteScenes(state.scenes)

  return (
    <Card title="Escenas rápidas">
      <p className={styles.narration ?? ''} role="status" aria-live="polite">
        {state.activationMessage ?? narrate(state, activeSceneId, favorites.length)}
      </p>

      {activationReason !== null && favorites.length > 0 && (
        <ControlNote id={reasonId}>{activationReason}</ControlNote>
      )}

      {favorites.length > 0 && (
        <ul className={styles.tiles ?? ''}>
          {favorites.map((scene) => {
            const active = scene.id === activeSceneId
            return (
              <li key={scene.id}>
                <Button
                  busy={state.pendingId === scene.id}
                  disabled={activationReason !== null}
                  describedBy={activationReason === null ? undefined : reasonId}
                  current={active}
                  ariaLabel={active ? `${scene.name}, activa` : `Activar ${scene.name}`}
                  onClick={() => {
                    catalog.activate(scene.id)
                  }}
                >
                  {scene.name}
                  {/* La marca no es solo el color: tambien se lee. */}
                  {active && <span className={styles.badge ?? ''}> · activa</span>}
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

function narrate(
  state: SceneCatalog['state'],
  activeSceneId: string | null,
  favorites: number,
): string {
  if (state.status === 'loading') return 'Cargando las escenas…'
  if (state.status === 'failed') return 'No se pudo cargar el catálogo de escenas.'

  const active = activeSceneId === null ? null : sceneName(state.scenes, activeSceneId)
  if (activeSceneId !== null) {
    return active === null
      ? 'Hay una escena activa que no está en el catálogo cargado.'
      : `Escena activa: «${active}».`
  }

  return favorites === 0
    ? 'Ninguna escena activa. Marca una escena como favorita en «Escenas» para tenerla aquí a un toque.'
    : 'Ninguna escena activa.'
}
