import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BrightnessSlider } from './BrightnessSlider'

describe('BrightnessSlider', () => {
  it('emite enteros 0-100', () => {
    const onChange = vi.fn()
    render(<BrightnessSlider value={40} disabled={false} onChange={onChange} />)

    fireEvent.change(screen.getByRole('slider'), { target: { value: '73' } })

    expect(onChange).toHaveBeenCalledWith(73)
  })

  it('sin la capacidad de brillo queda deshabilitado y explica por que', () => {
    render(
      <BrightnessSlider
        value={40}
        disabled
        disabledReason="El dispositivo conectado no admite el brillo."
        onChange={vi.fn()}
      />,
    )

    const slider = screen.getByRole('slider')
    const noteId = slider.getAttribute('aria-describedby')

    expect(slider).toHaveProperty('disabled', true)
    expect(noteId).not.toBeNull()
    // La explicacion existe, esta en la pagina y ademas esta ENLAZADA al
    // control: un texto suelto no lo anuncia un lector de pantalla.
    expect(document.getElementById(noteId ?? '')?.textContent).toBe(
      'El dispositivo conectado no admite el brillo.',
    )
  })

  it('no enlaza ninguna explicacion cuando el control esta operativo', () => {
    render(<BrightnessSlider value={40} disabled={false} onChange={vi.fn()} />)

    expect(screen.getByRole('slider').getAttribute('aria-describedby')).toBeNull()
  })
})
