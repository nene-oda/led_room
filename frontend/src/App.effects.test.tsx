import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { json, openSocket, stubBackend, EFFECT, STATE, type Route } from './test/backend'
import { FakeSocket } from './test/fakeSocket'

/**
 * Efectos de punta a punta, con el backend simulado en la frontera real.
 *
 * Se prueba lo que ve quien usa la aplicacion: que efecto suena, quien lo puede
 * arrancar y —lo que menos se espera— que tocar el color, el brillo o el
 * encendido lo detiene, porque eso lo decide el servidor y la pantalla no puede
 * ocultarlo.
 */

const START: Route = () => json({ running: true, id: EFFECT.id })
const STOP: Route = () => json(null)

const ROUTES: Record<string, Route> = {
  [`POST /api/v1/effects/${EFFECT.id}/start`]: START,
  [`POST /api/v1/effects/${EFFECT.id}/stop`]: STOP,
}

/** Abre el dialogo de efectos desde el boton de su tarjeta. */
function openDialog(): void {
  fireEvent.click(screen.getByRole('button', { name: 'Gestionar efectos' }))
}

/** El servidor confirma por `/ws` lo que hizo con el efecto. */
function emitEffect(type: 'effect.started' | 'effect.stopped', version: number): void {
  act(() => {
    FakeSocket.last.emit({ type, version, payload: { effect_id: EFFECT.id } })
  })
}

beforeEach(() => {
  FakeSocket.reset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('efectos', () => {
  it('sin ningun efecto sonando lo dice, en vez de callar', async () => {
    stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    expect(screen.getByText('No hay ningún efecto en marcha.')).toBeDefined()
  })

  it('arranca un efecto del catalogo y lo refleja cuando el servidor lo confirma', async () => {
    const fetchMock = stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    openDialog()
    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar Atardecer' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/effects/e1/start',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    // El indicador no se adelanta al servidor: cambia cuando llega su evento.
    emitEffect('effect.started', 4)

    expect(
      screen.getByText(/En marcha: «Atardecer»/),
    ).toBeDefined()
    // Y avisa de lo que pasara si se usa un control manual.
    expect(
      screen.getByText(/el efecto se detendrá/),
    ).toBeDefined()
    expect(screen.getByRole('button', { name: 'Detener Atardecer' })).toBeDefined()
  })

  it('un efecto arrancado desde otro cliente aparece igual', async () => {
    stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    emitEffect('effect.started', 4)

    expect(screen.getByText(/En marcha: «Atardecer»/)).toBeDefined()
  })

  it('lo detiene desde la barra y vuelve a decir que no hay nada sonando', async () => {
    const fetchMock = stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()
    emitEffect('effect.started', 4)

    fireEvent.click(screen.getByRole('button', { name: 'Detener el efecto Atardecer' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/effects/e1/stop',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    emitEffect('effect.stopped', 5)
    expect(screen.getByText('No hay ningún efecto en marcha.')).toBeDefined()
  })

  it('dice que el efecto se detuvo por un comando manual, en vez de apagarlo en silencio', async () => {
    stubBackend({
      ...ROUTES,
      'POST /api/v1/lights/power': () => json({ power: true, color: '#FF0000', brightness: 40 }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()
    emitEffect('effect.started', 4)

    // El usuario enciende la tira mientras suena el efecto: el servidor detiene
    // el efecto ANTES de aplicar el comando.
    fireEvent.click(screen.getByRole('switch', { name: /Apagada|Encendida/ }))
    emitEffect('effect.stopped', 5)

    expect(
      screen.getByText(/«Atardecer» se detuvo porque enviaste un comando manual/),
    ).toBeDefined()
  })

  it('un efecto que termina solo no se cuenta como cancelado por el usuario', async () => {
    stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()
    emitEffect('effect.started', 4)

    // Nadie toco nada: el efecto simplemente se agoto.
    emitEffect('effect.stopped', 5)

    expect(screen.getByText('No hay ningún efecto en marcha.')).toBeDefined()
  })

  it('hidrata el efecto en curso al abrir la aplicacion', async () => {
    stubBackend({
      ...ROUTES,
      'GET /api/v1/state': () => json({ ...STATE, effect: { running: true, id: EFFECT.id } }),
    })
    render(<App />)

    expect(await screen.findByText(/En marcha: «Atardecer»/)).toBeDefined()
  })

  it('sin dispositivo conectado no se puede arrancar, y se explica una sola vez', async () => {
    stubBackend({
      ...ROUTES,
      'GET /api/v1/state': () => json({ ...STATE, device: { ...STATE.device, connected: false } }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · desconectado')

    openDialog()
    const start = await screen.findByRole('button', { name: 'Iniciar Atardecer' })
    expect(start).toHaveProperty('disabled', true)

    const noteId = start.getAttribute('aria-describedby')
    expect(document.getElementById(noteId ?? '')?.textContent).toBe(
      'El dispositivo «Tira del salón» no está conectado.',
    )
  })

  it('avisa cuando el servidor rechaza la reproduccion, sin inventar la causa', async () => {
    stubBackend({
      ...ROUTES,
      [`POST /api/v1/effects/${EFFECT.id}/start`]: () =>
        json({ detail: { code: 'device_not_connected', message: 'sin enlace' } }, 409),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    openDialog()
    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar Atardecer' }))

    expect(await screen.findByText('No hay ningún dispositivo conectado.')).toBeDefined()
    expect(screen.getByText('No hay ningún efecto en marcha.')).toBeDefined()
  })
})

describe('catálogo de efectos', () => {
  it('crea un efecto nuevo y vuelve a leer el catálogo del servidor', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      'POST /api/v1/effects': () => json({ ...EFFECT, id: 'e2', name: 'Nocturno' }, 201),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    openDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo efecto' }))
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Nocturno' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear efecto' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/effects',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    const body: unknown = JSON.parse(
      String(
        fetchMock.mock.calls.find(
          (call) => call[0] === '/api/v1/effects' && call[1]?.method === 'POST',
        )?.[1]?.body,
      ),
    )
    // El cuerpo es el del contrato: sin `id` (lo pone el servidor) y con la
    // posicion de cada paso implicita en el orden del array.
    expect(body).toMatchObject({ name: 'Nocturno', type: 'SMOOTH_CYCLE' })
    expect(body).not.toHaveProperty('id')

    // El orden del catálogo lo decide el servidor: se relee en vez de colar la
    // respuesta en la lista.
    // Dos lecturas: la de la carga inicial y la de despues de guardar.
    const listCalls = fetchMock.mock.calls.filter(
      (call) => call[0] === '/api/v1/effects' && call[1]?.method === undefined,
    )
    expect(listCalls).toHaveLength(2)
  })

  it('relee el efecto antes de editarlo, porque el catálogo no viaja por el socket', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      [`GET /api/v1/effects/${EFFECT.id}`]: () => json({ ...EFFECT, name: 'Atardecer (v2)' }),
      [`PUT /api/v1/effects/${EFFECT.id}`]: () => json(EFFECT),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    openDialog()
    fireEvent.click(await screen.findByRole('button', { name: 'Editar Atardecer' }))

    // Lo que se edita es la copia autoritativa, no la de la lista.
    const name = await screen.findByLabelText('Nombre')
    await waitFor(() => {
      expect(name).toHaveProperty('value', 'Atardecer (v2)')
    })

    fireEvent.change(name, { target: { value: 'Atardecer largo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/effects/e1',
        expect.objectContaining({ method: 'PUT' }),
      )
    })
  })

  it('borrar pide confirmación en el propio botón', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      [`DELETE /api/v1/effects/${EFFECT.id}`]: () => new Response(null, { status: 204 }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    openDialog()
    fireEvent.click(await screen.findByRole('button', { name: 'Borrar Atardecer' }))

    expect(fetchMock).not.toHaveBeenCalledWith('/api/v1/effects/e1', expect.anything())

    fireEvent.click(screen.getByRole('button', { name: 'Confirmar el borrado de Atardecer' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/effects/e1',
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
  })
})
