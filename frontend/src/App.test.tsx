import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { json, openSocket, stubBackend, CAPABILITIES, DEVICE, STATE } from './test/backend'
import { FakeSocket } from './test/fakeSocket'

/**
 * Recorridos completos de la pantalla, con el backend simulado en la frontera
 * real: `fetch` para REST y un doble de `WebSocket` para el tiempo real.
 *
 * Se prueba lo que hace la aplicacion —hidratar, reconciliar, revertir, avisar,
 * deshabilitar por capacidades— y no como lo hace por dentro.
 */

beforeEach(() => {
  FakeSocket.reset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('pantalla principal', () => {
  it('se hidrata por REST y muestra las tres señales de conexion', async () => {
    stubBackend()
    render(<App />)

    expect(await screen.findByText('Tira del salón · conectado')).toBeDefined()
    expect(screen.getByText('Responde')).toBeDefined()
    expect(screen.getByText('Conectando…')).toBeDefined()

    await openSocket()
    expect(await screen.findByText('Conectado')).toBeDefined()

    expect(screen.getByRole('slider')).toHaveProperty('value', '40')
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false')
  })

  it('aplica los eventos del servidor sin que el usuario toque nada', async () => {
    stubBackend()
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    act(() => {
      FakeSocket.last.emit({
        type: 'light.brightness.changed',
        version: 4,
        payload: { brightness: 80 },
      })
      FakeSocket.last.emit({ type: 'light.power.changed', version: 5, payload: { power: true } })
    })

    expect(screen.getByRole('slider')).toHaveProperty('value', '80')
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true')
  })

  it('revierte el valor optimista y muestra el fallo cuando el servidor rechaza', async () => {
    stubBackend({
      'POST /api/v1/lights/power': () =>
        json({ detail: { code: 'device_not_connected', message: 'sin enlace' } }, 409),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    const toggle = screen.getByRole('switch')
    fireEvent.click(toggle)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('No hay ningún dispositivo conectado.')
    // Rollback: vuelve al ultimo estado que el servidor confirmo.
    expect(toggle.getAttribute('aria-checked')).toBe('false')
  })

  it('sin la capacidad de brillo, el control sale deshabilitado con explicacion', async () => {
    stubBackend({
      'GET /api/v1/devices': () =>
        json([{ ...DEVICE, capabilities: { ...CAPABILITIES, brightness: false } }]),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const slider = screen.getByRole('slider')
    await waitFor(() => {
      expect(slider).toHaveProperty('disabled', true)
    })

    const noteId = slider.getAttribute('aria-describedby')
    expect(document.getElementById(noteId ?? '')?.textContent).toBe(
      'El dispositivo conectado no admite el brillo.',
    )
    // El color, que si esta soportado, sigue operativo: la UI decide control a
    // control a partir de `capabilities`, no del tipo de adaptador.
    expect(screen.getByRole('group', { name: 'Selector de color' }).getAttribute('tabindex')).toBe(
      '0',
    )
  })

  it('sin dispositivo conectado deshabilita los controles y dice por que', async () => {
    stubBackend({
      'GET /api/v1/state': () =>
        json({ ...STATE, device: { ...STATE.device, connected: false } }),
    })
    render(<App />)

    expect(await screen.findByText('Tira del salón · desconectado')).toBeDefined()

    const toggle = screen.getByRole('switch')
    const noteId = toggle.getAttribute('aria-describedby')
    expect(toggle).toHaveProperty('disabled', true)
    expect(document.getElementById(noteId ?? '')?.textContent).toBe(
      'El dispositivo «Tira del salón» no está conectado.',
    )
  })

  it('el arrastre del color va por WebSocket y el cierre del gesto por REST', async () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 300,
      bottom: 100,
      width: 300,
      height: 100,
      toJSON: () => ({}),
    })
    const fetchMock = stubBackend({
      'PUT /api/v1/lights/color': () => json({ power: false, color: '#00FF00', brightness: 40 }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    const area = screen.getByRole('group', { name: 'Selector de color' })
    // Un tercio del ancho, arriba del todo: verde puro.
    fireEvent.pointerDown(area, { pointerId: 1, clientX: 100, clientY: 0 })

    expect(FakeSocket.last.sent).toEqual([
      '{"type":"light.color","payload":{"r":0,"g":255,"b":0}}',
    ])
    expect(fetchMock).not.toHaveBeenCalledWith('/api/v1/lights/color', expect.anything())

    fireEvent.pointerUp(area, { pointerId: 1, clientX: 100, clientY: 0 })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/lights/color',
        expect.objectContaining({ method: 'PUT' }),
      )
    })
  })

  it('avisa cuando el backend no responde, en vez de quedarse cargando', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))
    vi.stubGlobal('WebSocket', FakeSocket)
    render(<App />)

    expect(await screen.findByText('Sin respuesta')).toBeDefined()
    expect((await screen.findByRole('alert')).textContent).toContain(
      'No se pudo contactar con el servidor.',
    )
  })
})
