import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { json, openSocket, stubBackend, EFFECT, SCENE, type Route } from './test/backend'
import { FakeSocket } from './test/fakeSocket'

/**
 * Escenas de punta a punta, con el backend simulado en la frontera real.
 *
 * Se prueba lo que ve quien usa la aplicacion, y muy en especial las dos cosas
 * que una UI descuidada contaria mal:
 *
 *   - **la escena activa la dice el servidor**, no el boton que se acaba de
 *     pulsar;
 *   - **activar es atomico**: un 409 significa que no se reprodujo nada, nunca
 *     que se activo la mitad.
 */

/** El efecto `STATIC` que el servidor devuelve al crear un color fijo. */
const CREATED_EFFECT = {
  ...EFFECT,
  id: 'e2',
  name: 'Color fijo #FF9329',
  type: 'STATIC',
  loop: false,
  steps: [{ position: 0, color: '#FF9329', brightness: null, duration_ms: null, easing: null }],
}

const ROUTES: Record<string, Route> = {
  'POST /api/v1/scenes/s1/activate': () => json({ id: SCENE.id }),
}

/** El servidor confirma por `/ws` que la escena quedo puesta. */
function emitActivated(sceneId: string, version: number): void {
  act(() => {
    FakeSocket.last.emit({ type: 'scene.activated', version, payload: { scene_id: sceneId } })
  })
}

/** La barra siempre visible: es la unica region viva de las escenas. */
function quickBar() {
  return within(screen.getByRole('region', { name: 'Escenas rápidas' }))
}

/** El dialogo con la lista completa, que es donde vive el catalogo. */
function openLibrary() {
  fireEvent.click(screen.getByRole('button', { name: 'Gestionar escenas' }))
  return within(screen.getByRole('dialog', { name: 'Escenas' }))
}

beforeEach(() => {
  FakeSocket.reset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('escenas', () => {
  it('sin ninguna escena activa lo dice, en vez de callar', async () => {
    stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    expect(await quickBar().findByText('Ninguna escena activa.')).toBeDefined()
    // Y la favorita esta a un toque, fuera de cualquier panel plegado.
    expect(quickBar().getByRole('button', { name: 'Activar Noche' })).toBeDefined()
  })

  it('activa una escena y solo la marca cuando el servidor lo confirma', async () => {
    const fetchMock = stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    fireEvent.click(await quickBar().findByRole('button', { name: 'Activar Noche' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/scenes/s1/activate',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    // El indicador no se adelanta al servidor.
    expect(quickBar().queryByRole('button', { name: 'Noche, activa' })).toBeNull()

    emitActivated('s1', 4)

    expect(quickBar().getByRole('button', { name: 'Noche, activa' })).toBeDefined()
    expect(quickBar().getByText('Escena activa: «Noche».')).toBeDefined()
  })

  it('una escena activada desde otro cliente aparece igual', async () => {
    stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    emitActivated('s1', 4)

    expect(quickBar().getByText('Escena activa: «Noche».')).toBeDefined()
  })

  it('un 409 al activar dice que NO se activo nada, no que se activo a medias', async () => {
    stubBackend({
      ...ROUTES,
      'POST /api/v1/scenes/s1/activate': () =>
        json(
          {
            detail: {
              code: 'device_not_connected',
              message: 'La escena tiene un objetivo para otro dispositivo.',
            },
          },
          409,
        ),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    fireEvent.click(await quickBar().findByRole('button', { name: 'Activar Noche' }))

    expect(await quickBar().findByText(/No se activó nada/)).toBeDefined()
    expect(quickBar().getByText(/se activa entera o no se activa/)).toBeDefined()
    // Y nada quedo marcado como activo.
    expect(quickBar().queryByRole('button', { name: 'Noche, activa' })).toBeNull()
  })

  it('un fallo al activar desde el dialogo se lee dentro, no detras del modal', async () => {
    stubBackend({
      ...ROUTES,
      'POST /api/v1/scenes/s1/activate': () =>
        json(
          { detail: { code: 'device_not_connected', message: 'sin enlace' } },
          409,
        ),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    const library = openLibrary()
    fireEvent.click(await library.findByRole('button', { name: 'Activar Noche' }))

    // La barra de escenas rapidas sigue siendo la region viva de las escenas,
    // pero con el dialogo abierto queda tapada y fuera de `aria-modal`: el
    // fallo tiene que aparecer donde esta mirando quien acaba de pulsar.
    expect(await library.findByText(/No se activó nada/)).toBeDefined()
  })

  it('crear una escena de color fijo son DOS escrituras, y se avisa antes de guardar', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      'POST /api/v1/effects': () => json(CREATED_EFFECT, 201),
      'POST /api/v1/scenes': () => json(SCENE, 201),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const library = openLibrary()
    fireEvent.click(library.getByRole('button', { name: 'Nueva escena' }))

    // El aviso esta ANTES de guardar y nombra el efecto que va a aparecer en la
    // biblioteca: el atajo se ofrece, la normalizacion no se esconde.
    expect(await library.findByText(/se creará el efecto «Color fijo #FF9329»/)).toBeDefined()

    fireEvent.change(library.getByLabelText('Nombre'), { target: { value: 'Noche' } })
    fireEvent.click(library.getByRole('button', { name: 'Crear escena' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/scenes',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            name: 'Noche',
            description: null,
            icon: null,
            is_favorite: false,
            // El efecto se crea primero y la escena lo REFERENCIA: el contrato
            // no acepta un efecto incrustado.
            targets: [
              {
                device_id: 'a1',
                effect_id: 'e2',
                brightness: null,
                speed: null,
                enabled: true,
              },
            ],
          }),
        }),
      )
    })

    const effectCall = fetchMock.mock.calls.find(
      (call) => call[0] === '/api/v1/effects' && call[1]?.method === 'POST',
    )
    expect(effectCall).toBeDefined()
    expect(String(effectCall?.[1]?.body)).toContain('"name":"Color fijo #FF9329"')
    expect(String(effectCall?.[1]?.body)).toContain('"type":"STATIC"')
  })

  it('marcar como rapida reenvia la escena entera, porque PUT reemplaza', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      'GET /api/v1/scenes/s1': () => json(SCENE),
      'PUT /api/v1/scenes/s1': () => json({ ...SCENE, is_favorite: false }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const library = openLibrary()
    fireEvent.click(
      await library.findByRole('button', { name: 'Quitar Noche de las escenas rápidas' }),
    )

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/scenes/s1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({
            name: 'Noche',
            description: null,
            icon: null,
            is_favorite: false,
            targets: [
              { device_id: 'a1', effect_id: 'e1', brightness: null, speed: null, enabled: true },
            ],
          }),
        }),
      )
    })
  })

  it('duplica sin inventarse el nombre de la copia: lo pone el servidor', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      'POST /api/v1/scenes/s1/duplicate': () => json({ ...SCENE, id: 's2', name: 'Noche (copia)' }, 201),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const library = openLibrary()
    fireEvent.click(await library.findByRole('button', { name: 'Duplicar Noche' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/scenes/s1/duplicate',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    // Sin cuerpo: el sufijo de la copia es una regla del servidor y mandar un
    // nombre desde aqui seria una segunda definicion de la misma regla.
    const call = fetchMock.mock.calls.find((entry) => entry[0] === '/api/v1/scenes/s1/duplicate')
    expect(call?.[1]?.body).toBeUndefined()
  })

  it('borrar pide confirmacion en el propio boton', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      'DELETE /api/v1/scenes/s1': () => new Response(null, { status: 204 }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const library = openLibrary()
    fireEvent.click(await library.findByRole('button', { name: 'Borrar Noche' }))

    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/v1/scenes/s1',
      expect.objectContaining({ method: 'DELETE' }),
    )

    fireEvent.click(library.getByRole('button', { name: 'Confirmar el borrado de Noche' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/scenes/s1',
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
  })

  it('sin dispositivo conectado explica por que no se puede activar, en vez de fallar', async () => {
    stubBackend({
      ...ROUTES,
      'GET /api/v1/state': () =>
        json({
          version: 3,
          device: { device_id: 'a1', connected: false, rssi: null, last_error: null },
          light: { power: false, color: '#FF0000', brightness: 40 },
          effect: null,
          scene: null,
        }),
    })
    render(<App />)
    await screen.findByText('Tira del salón · desconectado')

    expect(await quickBar().findByText(/no está conectado/)).toBeDefined()
    expect(quickBar().getByRole('button', { name: 'Activar Noche' })).toHaveProperty(
      'disabled',
      true,
    )
  })
})
