import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EffectEditor } from './EffectEditor'
import { newEffectDraft } from '../../domain/effects'

/**
 * El editor de un efecto.
 *
 * Se prueba lo que el usuario puede hacer y lo que la pantalla le explica, no
 * como esta montado: que no se puede guardar algo que el servidor rechazaria,
 * que cambiar de algoritmo adapta la paleta y que la velocidad no se lee como
 * una duracion.
 */

function renderEditor(overrides: Partial<Parameters<typeof EffectEditor>[0]> = {}) {
  const onSave = vi.fn()
  const onCancel = vi.fn()

  render(
    <EffectEditor
      initial={newEffectDraft()}
      existing={false}
      saving={false}
      onSave={onSave}
      onCancel={onCancel}
      {...overrides}
    />,
  )

  return { onSave, onCancel }
}

function saveButton(): HTMLElement {
  return screen.getByRole('button', { name: 'Crear efecto' })
}

describe('editor de efectos', () => {
  it('no deja guardar sin nombre y dice por que', () => {
    const { onSave } = renderEditor()

    const button = saveButton()
    expect(button).toHaveProperty('disabled', true)

    const name = screen.getByLabelText('Nombre')
    const noteId = name.getAttribute('aria-describedby')
    expect(document.getElementById(noteId ?? '')?.textContent).toBe(
      'El efecto necesita un nombre.',
    )

    fireEvent.click(button)
    expect(onSave).not.toHaveBeenCalled()
  })

  it('guarda el borrador cuando es valido', () => {
    const { onSave } = renderEditor()

    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Atardecer' } })
    fireEvent.click(saveButton())

    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave.mock.calls[0]?.[0]).toMatchObject({ name: 'Atardecer', type: 'SMOOTH_CYCLE' })
  })

  it('el tipo es el algoritmo y la paleta se adapta a lo que admite', () => {
    renderEditor()

    // Dos colores mientras es un ciclo suave: con uno solo no hay transicion.
    expect(screen.getAllByRole('button', { name: /^Color \d de la paleta/ })).toHaveLength(2)

    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'STATIC' } })

    expect(screen.getAllByRole('button', { name: /^Color \d de la paleta/ })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Añadir color' })).toHaveProperty('disabled', true)
  })

  it('«Fijo» no se repite y lo explica en vez de dejar el interruptor mudo', () => {
    renderEditor()
    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'STATIC' } })

    const loop = screen.getByRole('switch', { name: /Repetir en bucle/ })
    const noteId = loop.getAttribute('aria-describedby')
    expect(loop).toHaveProperty('disabled', true)
    expect(document.getElementById(noteId ?? '')?.textContent).toContain('no se repite')
  })

  it('el brillo mínimo solo aparece donde hay envolvente', () => {
    renderEditor()

    expect(screen.queryByLabelText('Brillo mínimo')).toBeNull()
    expect(screen.getByLabelText('Brillo')).toBeDefined()

    fireEvent.change(screen.getByLabelText('Tipo'), { target: { value: 'PULSE' } })

    expect(screen.getByLabelText('Brillo mínimo')).toBeDefined()
    expect(screen.getByLabelText('Brillo máximo')).toBeDefined()
  })

  it('enseña la duracion resultante para que la velocidad no se lea como tiempo', () => {
    renderEditor()

    // 1000 ms de base a velocidad 50 -> x1,00 -> 1,0 s.
    expect(screen.getByText(/Cada transición durará 1,0 s/)).toBeDefined()

    fireEvent.change(screen.getByLabelText('Velocidad'), { target: { value: '100' } })

    // Velocidad 100 NO son 100 ms: es la mitad de la duracion base.
    expect(screen.getByText(/Cada transición durará 0,5 s/)).toBeDefined()
  })
})
