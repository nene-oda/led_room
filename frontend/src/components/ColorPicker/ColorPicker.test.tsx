import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ColorPicker } from './ColorPicker'
import { rgb, toHex } from '../../domain/color'

/**
 * jsdom no hace layout: sin esto todos los rectangulos miden 0x0 y el control
 * no podria traducir una coordenada a un color.
 */
function stubArea(width = 200, height = 100): void {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: width,
    bottom: height,
    width,
    height,
    toJSON: () => ({}),
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ColorPicker', () => {
  it('traduce la posicion del puntero a un color de dominio', () => {
    stubArea()
    const onPreview = vi.fn()
    render(
      <ColorPicker
        color={rgb(255, 0, 0)}
        disabled={false}
        onPreview={onPreview}
        onCommit={vi.fn()}
      />,
    )

    // Extremo izquierdo y arriba del todo: tono 0, saturacion 1 => rojo puro.
    fireEvent.pointerDown(screen.getByRole('group', { name: 'Selector de color' }), {
      pointerId: 1,
      clientX: 0,
      clientY: 0,
    })

    expect(onPreview).toHaveBeenCalledWith(rgb(255, 0, 0))
  })

  it('el arrastre previsualiza y soltar cierra el gesto', () => {
    stubArea()
    const onPreview = vi.fn()
    const onCommit = vi.fn()
    render(
      <ColorPicker color={rgb(255, 0, 0)} disabled={false} onPreview={onPreview} onCommit={onCommit} />,
    )
    const area = screen.getByRole('group', { name: 'Selector de color' })

    fireEvent.pointerDown(area, { pointerId: 1, clientX: 0, clientY: 0 })
    // Un tercio del ancho: tono 120 => verde puro.
    fireEvent.pointerMove(area, { pointerId: 1, clientX: 200 / 3, clientY: 0 })
    fireEvent.pointerUp(area, { pointerId: 1, clientX: 200 / 3, clientY: 0 })

    expect(onPreview).toHaveBeenLastCalledWith(rgb(0, 255, 0))
    // El ultimo valor del gesto SIEMPRE se persiste: es lo que sobrevive al
    // reinicio, porque el arrastre por WebSocket no guarda nada.
    expect(onCommit).toHaveBeenCalledExactlyOnceWith(rgb(0, 255, 0))
  })

  it('no reacciona al movimiento si no hay un arrastre en curso', () => {
    stubArea()
    const onPreview = vi.fn()
    render(
      <ColorPicker color={rgb(255, 0, 0)} disabled={false} onPreview={onPreview} onCommit={vi.fn()} />,
    )

    fireEvent.pointerMove(screen.getByRole('group', { name: 'Selector de color' }), {
      pointerId: 1,
      clientX: 100,
      clientY: 50,
    })

    expect(onPreview).not.toHaveBeenCalled()
  })

  it('es operable con las flechas del teclado', () => {
    const onPreview = vi.fn()
    render(
      <ColorPicker color={rgb(255, 0, 0)} disabled={false} onPreview={onPreview} onCommit={vi.fn()} />,
    )

    fireEvent.keyDown(screen.getByRole('group', { name: 'Selector de color' }), {
      key: 'ArrowRight',
    })

    expect(onPreview).toHaveBeenCalledTimes(1)
    expect(onPreview.mock.calls[0]?.[0]).not.toEqual(rgb(255, 0, 0))
  })

  it('deshabilitado no emite nada, sale del orden de tabulacion y explica por que', () => {
    stubArea()
    const onPreview = vi.fn()
    render(
      <ColorPicker
        color={rgb(255, 0, 0)}
        disabled
        disabledReason="El dispositivo conectado no admite el color."
        onPreview={onPreview}
        onCommit={vi.fn()}
      />,
    )
    const area = screen.getByRole('group', { name: 'Selector de color' })

    fireEvent.pointerDown(area, { pointerId: 1, clientX: 10, clientY: 10 })
    fireEvent.keyDown(area, { key: 'ArrowRight' })

    expect(onPreview).not.toHaveBeenCalled()
    expect(area.getAttribute('tabindex')).toBe('-1')
    expect(area.getAttribute('aria-describedby')).toContain(' ')
    expect(screen.getByText('El dispositivo conectado no admite el color.')).toBeDefined()
  })

  it('muestra el color aplicado en una region viva', () => {
    render(
      <ColorPicker color={rgb(0, 0, 255)} disabled={false} onPreview={vi.fn()} onCommit={vi.fn()} />,
    )

    expect(screen.getByRole('status').textContent).toContain(toHex(rgb(0, 0, 255)))
  })
})
