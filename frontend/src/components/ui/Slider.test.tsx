import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Slider } from './Slider'

describe('Slider', () => {
  it('asocia la etiqueta visible con el control', () => {
    render(<Slider label="Brillo" value={40} onChange={vi.fn()} />)

    expect(screen.getByLabelText('Brillo')).toBe(screen.getByRole('slider'))
  })

  it('anuncia el valor como porcentaje en aria-valuetext', () => {
    render(<Slider label="Brillo" value={40} onChange={vi.fn()} />)

    expect(screen.getByRole('slider')).toHaveProperty('ariaValueText', '40 %')
  })

  it('permite sustituir el texto del valor cuando el rango no es un porcentaje', () => {
    render(<Slider label="Velocidad" value={3} max={10} valueText="3 de 10" onChange={vi.fn()} />)

    expect(screen.getByRole('slider')).toHaveProperty('ariaValueText', '3 de 10')
  })

  it('emite el nuevo valor como numero', () => {
    const onChange = vi.fn()
    render(<Slider label="Brillo" value={40} onChange={onChange} />)

    fireEvent.change(screen.getByRole('slider'), { target: { value: '75' } })

    expect(onChange).toHaveBeenCalledWith(75)
  })

  it('expone el rango 0-100 entero por defecto', () => {
    render(<Slider label="Brillo" value={40} onChange={vi.fn()} />)
    const slider = screen.getByRole('slider')

    expect(slider).toHaveProperty('min', '0')
    expect(slider).toHaveProperty('max', '100')
    expect(slider).toHaveProperty('step', '1')
  })

  it('queda deshabilitado y enlazado a la explicacion del motivo', () => {
    // El navegador no entrega eventos a un control deshabilitado, asi que la
    // garantia esta en el atributo; `fireEvent` los inyecta igualmente y
    // comprobar la ausencia de llamada solo probaria jsdom.
    render(
      <>
        <p id="motivo">El dispositivo no soporta brillo</p>
        <Slider label="Brillo" value={40} onChange={vi.fn()} disabled describedBy="motivo" />
      </>,
    )
    const slider = screen.getByRole('slider')

    expect(slider).toHaveProperty('disabled', true)
    expect(slider.getAttribute('aria-describedby')).toBe('motivo')
  })
})
