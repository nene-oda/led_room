import { useState } from 'react'

import styles from './EffectLibrary.module.css'
import catalog from '../ui/catalog.module.css'
import { toHex } from '../../domain/color'
import { EFFECT_TYPE_SPECS, formatSeconds, transitionDurationMs, type Effect } from '../../domain/effects'
import { Button } from '../ui/Button'

export interface EffectRowProps {
  readonly effect: Effect
  readonly running: boolean
  /** Hay una operacion en curso sobre este efecto. */
  readonly busy: boolean
  /**
   * Id del texto que explica por que no se puede reproducir; `null` = se puede.
   *
   * Un id y no el texto: el motivo es el mismo para toda la lista (no hay
   * dispositivo, no esta conectado, no admite color), asi que se escribe una
   * vez en el panel y cada boton apunta a el. Repetirlo por fila obligaria a
   * un lector de pantalla a oir seis veces lo mismo.
   */
  readonly playbackBlockedBy: string | null
  readonly onStart: (effectId: string) => void
  readonly onStop: (effectId: string) => void
  readonly onEdit: (effectId: string) => void
  readonly onDelete: (effectId: string) => void
}

/**
 * Un efecto del catalogo.
 *
 * Arrancar es la accion principal y esta primero; editar y borrar van despues,
 * porque activar es lo que se hace a diario y editar lo que se hace una vez.
 *
 * **Borrar pide confirmacion en el propio boton** en vez de abrir un dialogo:
 * es irreversible y con el pulgar se pulsa sin querer, pero un modal obligaria
 * a reimplementar trampa de foco y Escape para una lista.
 *
 * No lleva region viva: el estado "en marcha" lo anuncia `EffectStatusBar`, que
 * es la unica, para que arrancar un efecto no produzca dos anuncios.
 */
export function EffectRow({
  effect,
  running,
  busy,
  playbackBlockedBy,
  onStart,
  onStop,
  onEdit,
  onDelete,
}: EffectRowProps) {
  const [confirming, setConfirming] = useState(false)
  const spec = EFFECT_TYPE_SPECS[effect.type]

  return (
    <li className={catalog.row ?? ''}>
      <div className={catalog.rowMain ?? ''}>
        <span className={catalog.name ?? ''}>
          {effect.name}
          {running && <span className={catalog.badge ?? ''}> · en marcha</span>}
          {effect.isBuiltin && <span className={catalog.badge ?? ''}> · de fábrica</span>}
        </span>

        <span className={catalog.meta ?? ''}>
          <span>{spec.label}</span>
          <span>{formatSeconds(transitionDurationMs(effect))} por transición</span>
          {effect.loop && <span>en bucle</span>}
        </span>

        {/* La paleta se ve de un vistazo: es lo que distingue dos efectos del
            mismo tipo. Decorativa: el detalle lo da el editor. */}
        <span className={styles.paletteStrip ?? ''} aria-hidden="true">
          {effect.steps.map((step, index) => (
            <span
              key={`${String(index)}-${toHex(step.color)}`}
              className={styles.chip ?? ''}
              style={{ backgroundColor: toHex(step.color) }}
            />
          ))}
        </span>
      </div>

      <div className={catalog.actions ?? ''}>
        {running ? (
          <Button
            busy={busy}
            ariaLabel={`Detener ${effect.name}`}
            onClick={() => {
              onStop(effect.id)
            }}
          >
            Detener
          </Button>
        ) : (
          <Button
            busy={busy}
            disabled={playbackBlockedBy !== null}
            describedBy={playbackBlockedBy ?? undefined}
            ariaLabel={`Iniciar ${effect.name}`}
            onClick={() => {
              onStart(effect.id)
            }}
          >
            Iniciar
          </Button>
        )}

        <Button
          busy={busy}
          ariaLabel={`Editar ${effect.name}`}
          onClick={() => {
            onEdit(effect.id)
          }}
        >
          Editar
        </Button>

        <Button
          busy={busy}
          ariaLabel={
            confirming ? `Confirmar el borrado de ${effect.name}` : `Borrar ${effect.name}`
          }
          onClick={() => {
            if (confirming) onDelete(effect.id)
            else setConfirming(true)
          }}
        >
          {confirming ? 'Confirmar' : 'Borrar'}
        </Button>
      </div>
    </li>
  )
}
