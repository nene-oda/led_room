import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ColorPresetGrid } from './ColorPresetGrid'
import { rgb } from '../../domain/color'
import type { ColorPreset } from '../../domain/presets'

const PRESETS: readonly ColorPreset[] = [
  { name: 'Rojo', color: rgb(255, 0, 0) },
  { name: 'Azul', color: rgb(0, 0, 255) },
]

describe('ColorPresetGrid', () => {
  it('activa un color con una sola pulsacion', () => {
    const onSelect = vi.fn()
    render(
      <ColorPresetGrid presets={PRESETS} current={rgb(0, 0, 0)} disabled={false} onSelect={onSelect} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Azul' }))

    expect(onSelect).toHaveBeenCalledWith(rgb(0, 0, 255))
  })

  it('marca cual coincide con el color aplicado', () => {
    render(
      <ColorPresetGrid presets={PRESETS} current={rgb(255, 0, 0)} disabled={false} onSelect={vi.fn()} />,
    )

    expect(screen.getByRole('button', { name: 'Rojo' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Azul' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('sin la capacidad de color queda deshabilitado y enlaza la explicacion', () => {
    render(
      <ColorPresetGrid
        presets={PRESETS}
        current={rgb(255, 0, 0)}
        disabled
        disabledReason="El dispositivo conectado no admite el color."
        onSelect={vi.fn()}
      />,
    )
    const swatch = screen.getByRole('button', { name: 'Rojo' })
    const noteId = swatch.getAttribute('aria-describedby')

    expect(swatch).toHaveProperty('disabled', true)
    expect(document.getElementById(noteId ?? '')?.textContent).toBe(
      'El dispositivo conectado no admite el color.',
    )
  })
})
