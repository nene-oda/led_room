import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Toggle } from './Toggle'

describe('Toggle', () => {
  it('se expone como interruptor con su estado', () => {
    render(<Toggle label="Encendido" checked onChange={vi.fn()} />)

    expect(screen.getByRole('switch', { name: 'Encendido' }).getAttribute('aria-checked')).toBe(
      'true',
    )
  })

  it('es un boton nativo, asi que responde al teclado sin codigo propio', () => {
    render(<Toggle label="Encendido" checked={false} onChange={vi.fn()} />)

    expect(screen.getByRole('switch').tagName).toBe('BUTTON')
  })

  it('pide el estado contrario al actual', () => {
    const onChange = vi.fn()
    render(<Toggle label="Encendido" checked={false} onChange={onChange} />)

    fireEvent.click(screen.getByRole('switch'))

    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('no invierte el estado por su cuenta: espera a que el llamante lo confirme', () => {
    render(<Toggle label="Encendido" checked={false} onChange={vi.fn()} />)
    const toggle = screen.getByRole('switch')

    fireEvent.click(toggle)

    expect(toggle.getAttribute('aria-checked')).toBe('false')
  })

  it('no emite nada cuando esta deshabilitado y enlaza su explicacion', () => {
    const onChange = vi.fn()
    render(
      <>
        <p id="motivo">Sin dispositivo conectado</p>
        <Toggle label="Encendido" checked={false} onChange={onChange} disabled describedBy="motivo" />
      </>,
    )
    const toggle = screen.getByRole('switch')

    expect(toggle.getAttribute('aria-describedby')).toBe('motivo')

    fireEvent.click(toggle)
    expect(onChange).not.toHaveBeenCalled()
  })
})
