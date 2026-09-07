import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { json, openSocket, stubBackend, PROFILE, SCENE, type Route } from './test/backend'
import { FakeSocket } from './test/fakeSocket'

/**
 * Perfiles de punta a punta.
 *
 * Lo que estos recorridos protegen es que la pantalla no invente un estado que
 * el servidor no guarda: **no hay "perfil activo"**. Activar un perfil es
 * activar su escena predeterminada, asi que lo que queda marcado es la escena,
 * y los errores son los mismos que los de activarla directamente.
 */

const ROUTES: Record<string, Route> = {
  'POST /api/v1/profiles/p1/activate': () => json({ profile_id: 'p1', scene: { id: 's1' } }),
}

/**
 * Abre el dialogo de perfiles y devuelve su ambito.
 *
 * El ambito es el `dialog` y no la tarjeta: la lista y el editor viven dentro
 * del modal, y la tarjeta solo conserva el resumen y el boton.
 */
function openDialog() {
  fireEvent.click(screen.getByRole('button', { name: 'Gestionar perfiles' }))
  return within(screen.getByRole('dialog', { name: 'Perfiles' }))
}

function quickBar() {
  return within(screen.getByRole('region', { name: 'Escenas rápidas' }))
}

beforeEach(() => {
  FakeSocket.reset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('perfiles', () => {
  it('dice que escena activaria cada perfil, sin recalcular el desempate', async () => {
    stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const dialog = openDialog()

    // `default_scene_id` viene resuelto del servidor; aqui solo se nombra.
    expect(await dialog.findByText('1 escena · activa «Noche»')).toBeDefined()
  })

  it('activar un perfil marca su escena, y solo cuando el servidor lo confirma', async () => {
    const fetchMock = stubBackend(ROUTES)
    render(<App />)
    await screen.findByText('Tira del salón · conectado')
    await openSocket()

    const dialog = openDialog()
    fireEvent.click(await dialog.findByRole('button', { name: 'Activar Cine' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/profiles/p1/activate',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    expect(quickBar().getByText('Ninguna escena activa.')).toBeDefined()

    // El servidor difunde `scene.activated`, no un evento de perfil: es la
    // misma operacion y la misma ranura del estado global.
    act(() => {
      FakeSocket.last.emit({ type: 'scene.activated', version: 4, payload: { scene_id: 's1' } })
    })

    expect(quickBar().getByText('Escena activa: «Noche».')).toBeDefined()
    expect(screen.getByText('1 escena · activa «Noche», que está puesta')).toBeDefined()
  })

  it('un perfil sin escenas no se puede activar, y lo dice antes de intentarlo', async () => {
    stubBackend({
      ...ROUTES,
      'GET /api/v1/profiles': () => json([{ ...PROFILE, scenes: [], default_scene_id: null }]),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const dialog = openDialog()

    expect(await dialog.findByText('Sin escenas: todavía no se puede activar')).toBeDefined()
    expect(dialog.getByRole('button', { name: 'Activar Cine' })).toHaveProperty('disabled', true)
  })

  it('un 409 al activar hereda el mensaje de la escena: no se activo nada', async () => {
    stubBackend({
      ...ROUTES,
      'POST /api/v1/profiles/p1/activate': () =>
        json(
          { detail: { code: 'unsupported_capability', message: 'Falta una capacidad.' } },
          409,
        ),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const dialog = openDialog()
    fireEvent.click(await dialog.findByRole('button', { name: 'Activar Cine' }))

    expect(await dialog.findByText(/No se activó nada/)).toBeDefined()
  })

  it('crea un perfil eligiendo sus escenas y cual es la predeterminada', async () => {
    const fetchMock = stubBackend({
      ...ROUTES,
      'GET /api/v1/scenes': () => json([SCENE, { ...SCENE, id: 's2', name: 'Tarde' }]),
      'POST /api/v1/profiles': () => json(PROFILE, 201),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    const dialog = openDialog()
    fireEvent.click(dialog.getByRole('button', { name: 'Nuevo perfil' }))

    fireEvent.change(dialog.getByLabelText('Nombre'), { target: { value: 'Cine' } })

    // Un perfil sin escenas no se puede guardar: activarlo daria 409.
    expect(dialog.getByRole('button', { name: 'Crear perfil' })).toHaveProperty('disabled', true)

    fireEvent.click(dialog.getByLabelText('Noche'))
    fireEvent.click(dialog.getByLabelText('Tarde'))
    // La primera queda predeterminada sola; se cambia a la segunda a mano.
    fireEvent.click(dialog.getAllByLabelText('Predeterminada')[1] as HTMLElement)

    fireEvent.click(dialog.getByRole('button', { name: 'Crear perfil' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/profiles',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            name: 'Cine',
            description: null,
            icon: null,
            // Sin `position`: la posicion ES el indice del array.
            scenes: [
              { scene_id: 's1', is_default: false },
              { scene_id: 's2', is_default: true },
            ],
          }),
        }),
      )
    })
  })
})
