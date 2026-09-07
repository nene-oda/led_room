import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ModalCard } from './ModalCard'

/**
 * Lo que `ModalCard` añade sobre `Modal`: el resumen que se lee sin abrir nada,
 * el boton que abre y el aviso de cierre. El comportamiento del dialogo en si
 * se prueba en `Modal.test.tsx` y no se repite aqui.
 */
describe('ModalCard', () => {
  it('deja ver el resumen sin abrir el dialogo', () => {
    render(
      <ModalCard
        title="Escenas"
        summary="3 guardadas"
        actionText="Gestionar"
        actionLabel="Gestionar escenas"
      >
        <p>Lista completa</p>
      </ModalCard>,
    )

    expect(screen.getByRole('region', { name: 'Escenas' })).toBeDefined()
    expect(screen.getByText('3 guardadas')).toBeDefined()
    // La tarjeta es un resumen accionable: el contenido pesado no esta montado.
    expect(screen.queryByText('Lista completa')).toBeNull()
  })

  it('distingue los cinco botones «Gestionar» por su nombre accesible', () => {
    render(
      <ModalCard
        title="Perfiles"
        summary="2 guardados"
        actionText="Gestionar"
        actionLabel="Gestionar perfiles"
      >
        <p>Lista completa</p>
      </ModalCard>,
    )

    const action = screen.getByRole('button', { name: 'Gestionar perfiles' })
    expect(action.textContent).toBe('Gestionar')
  })

  it('avisa al cerrar, para que quien lo usa pueda descartar lo que quedo a medias', () => {
    const onClose = vi.fn()
    render(
      <ModalCard
        title="Efectos"
        summary="1 guardado"
        actionText="Gestionar"
        actionLabel="Gestionar efectos"
        onClose={onClose}
      >
        <p>Editor</p>
      </ModalCard>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Gestionar efectos' }))
    expect(screen.getByText('Editor')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar Efectos' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Editor')).toBeNull()
  })
})
