import { useId } from 'react'

import { EffectEditor } from './EffectEditor'
import { EffectRow } from './EffectRow'
import styles from '../ui/catalog.module.css'
import type { EffectCatalog } from '../../hooks/useEffectCatalog'
import { Button } from '../ui/Button'
import { ControlNote } from '../ui/ControlNote'
import { ModalCard } from '../ui/ModalCard'

export interface EffectLibraryProps {
  /**
   * Catalogo y acciones, tal y como los expone `useEffectCatalog`.
   *
   * Se pasa entero en vez de repartido en ocho props porque es **un solo
   * concepto** —la biblioteca de efectos— y desmontarlo aqui solo produciria
   * una lista de devoluciones que este componente se limitaria a reenviar.
   */
  readonly catalog: EffectCatalog
  /** Efecto que el servidor esta reproduciendo. Viene del estado compartido. */
  readonly runningId: string | null
  /** Por que no se puede reproducir nada ahora mismo. `null` = se puede. */
  readonly playbackReason: string | null
}

/**
 * La biblioteca de efectos: listar, arrancar, parar, crear, editar y borrar.
 *
 * Dentro de un dialogo, igual que las otras bibliotecas y por el mismo motivo:
 * crear y editar se hace una vez, y el control diario —encendido, color,
 * brillo— tiene que seguir a la vista y alcanzable con el pulgar. Lo que **no**
 * se esconde es el estado del efecto en curso, que tiene su propia tarjeta
 * (`EffectStatusBar`): hace falta verlo con el dialogo cerrado.
 *
 * El indicador de "que esta sonando" no se guarda aqui: llega del estado
 * compartido, que es lo unico que el WebSocket mantiene al dia.
 */
export function EffectLibrary({ catalog, runningId, playbackReason }: EffectLibraryProps) {
  const reasonId = useId()
  const { state } = catalog

  return (
    <ModalCard
      title="Efectos"
      summary={summarize(state.effects.length)}
      actionText="Gestionar"
      actionLabel="Gestionar efectos"
      // Un borrador a medias no se pierde por un clic torpe en el fondo.
      dismissOnBackdrop={state.editing === null}
      // Cerrar descarta lo que estaba a medias: el borrador vive en el hook,
      // que sobrevive al dialogo, y reaparecer al abrir seria una sorpresa.
      onClose={catalog.cancelEdit}
    >
      {/* Region viva del dialogo: cuenta cargas y fallos. El efecto en curso lo
          anuncia su tarjeta, no esta. */}
      <p className={styles.narration ?? ''} role="status" aria-live="polite">
        {state.message ?? narrate(state.status, state.effects.length)}
      </p>

      {/* El motivo se escribe UNA vez y todos los botones deshabilitados
          apuntan a el con `aria-describedby`. */}
      {playbackReason !== null && <ControlNote id={reasonId}>{playbackReason}</ControlNote>}

      <ul className={styles.list ?? ''}>
        {state.effects.map((effect) => (
          <EffectRow
            key={effect.id}
            effect={effect}
            running={effect.id === runningId}
            busy={state.pendingId === effect.id}
            playbackBlockedBy={playbackReason === null ? null : reasonId}
            onStart={catalog.start}
            onStop={catalog.stop}
            onEdit={catalog.edit}
            onDelete={catalog.remove}
          />
        ))}
      </ul>

      <Button disabled={state.editing !== null} onClick={catalog.create}>
        Nuevo efecto
      </Button>

      {state.editing !== null && (
        // `key` reinicia el formulario al cambiar de efecto: sin el, abrir otro
        // reutilizaria el borrador del anterior.
        <EffectEditor
          key={state.editing.id ?? 'new'}
          initial={state.editing.draft}
          existing={state.editing.id !== null}
          saving={state.saving}
          onSave={catalog.save}
          onCancel={catalog.cancelEdit}
        />
      )}
    </ModalCard>
  )
}

function summarize(count: number): string {
  return count === 1 ? '1 guardado' : `${String(count)} guardados`
}

function narrate(status: 'loading' | 'ready' | 'failed', count: number): string {
  switch (status) {
    case 'loading':
      return 'Cargando el catálogo de efectos…'
    case 'failed':
      // Con este estado siempre hay `message`; esto solo cierra el tipo.
      return 'No se pudo cargar el catálogo de efectos.'
    case 'ready':
      return count === 0
        ? 'Todavía no hay ningún efecto guardado. Crea uno para empezar.'
        : `${String(count)} ${count === 1 ? 'efecto guardado' : 'efectos guardados'}.`
  }
}
