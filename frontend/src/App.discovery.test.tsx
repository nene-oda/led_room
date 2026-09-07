import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import {
  json,
  stubBackend,
  DEVICE,
  STATE,
  SYSTEM,
  SYSTEM_WITHOUT_RADIO,
  type Route,
} from './test/backend'
import { FakeSocket } from './test/fakeSocket'
import { MIN_VISIBLE_SCAN_MS } from './domain/discovery'

/**
 * Alta y enlace de un dispositivo, de punta a punta.
 *
 * Es el camino que recorre alguien que acaba de abrir la aplicacion y todavia
 * no tiene su tira dada de alta. Se prueba lo que ve y lo que puede hacer, no
 * como esta montado por dentro.
 */

const SCAN = 'GET /api/v1/devices/scan?timeout=10'
const SYSTEM_ROUTE = 'GET /api/v1/system'

const NEAR = { name: 'LotusLantern', address: 'AA:BB:CC:DD:EE:F2', rssi: -45 }
const FAR = { name: 'ELK-BLEDOM', address: 'AA:BB:CC:DD:EE:F1', rssi: -80 }

/** Estado inicial de quien todavia no tiene nada dado de alta. */
const EMPTY_ROUTES: Record<string, Route> = {
  'GET /api/v1/devices': () => json([]),
  'GET /api/v1/state': () => json({ ...STATE, device: null }),
}

/** Abre el dialogo de dispositivos desde el boton de su tarjeta. */
function openDialog(): void {
  fireEvent.click(screen.getByRole('button', { name: 'Gestionar dispositivos' }))
}

function scanButton(): HTMLElement {
  return screen.getByRole('button', { name: /Buscar dispositivos|Buscando/ })
}

beforeEach(() => {
  FakeSocket.reset()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('alta de dispositivos', () => {
  it('muestra los resultados del escaneo ordenados por cercania', async () => {
    stubBackend({ ...EMPTY_ROUTES, [SCAN]: () => json([FAR, NEAR]) })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    expect(await screen.findByText('2 dispositivos encontrados.')).toBeDefined()

    // Lo mas cercano primero: con dos tiras del mismo modelo, la señal es la
    // unica pista practica de cual es la de esta habitacion.
    const offers = screen.getAllByRole('button', { name: /^Registrar y conectar/ })
    expect(offers.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Registrar y conectar LotusLantern',
      'Registrar y conectar ELK-BLEDOM',
    ])
    expect(screen.getByText('Cerca')).toBeDefined()
    expect(screen.getByText('Lejos')).toBeDefined()
  })

  it('enseña las direcciones recortadas hasta que se piden enteras', async () => {
    stubBackend({ ...EMPTY_ROUTES, [SCAN]: () => json([NEAR]) })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())
    await screen.findByText('1 dispositivo encontrado.')

    expect(screen.getByText('AA:B…E:F2')).toBeDefined()
    expect(screen.queryByText(NEAR.address)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Mostrar direcciones completas' }))

    expect(screen.getByText(NEAR.address)).toBeDefined()
  })

  it('si el servidor no dice si tiene radio, la lista vacia no afirma una causa', async () => {
    // Sin `GET /system` (backend antiguo o inalcanzable) la lista vacia sigue
    // teniendo dos causas posibles: no hay tiras cerca, o el servidor corre con
    // el adaptador nulo. Se nombran las dos en vez de elegir una.
    stubBackend({ ...EMPTY_ROUTES, [SCAN]: () => json([]) })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    const narration = await screen.findByText(/El escaneo terminó sin resultados/)
    expect(narration.textContent).toContain('adaptador nulo')
    expect(narration.textContent).toContain('no tiene radio Bluetooth')
  })

  it('con radio confirmada, la lista vacia dice lo unico que puede significar', async () => {
    stubBackend({
      ...EMPTY_ROUTES,
      [SYSTEM_ROUTE]: () => json(SYSTEM),
      [SCAN]: () => json([]),
    })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    // La ambiguedad la resuelve `/system`: con radio, cero resultados solo
    // puede querer decir que no hay ninguna tira al alcance.
    const narration = await screen.findByText(/no hay ninguna tira encendida al alcance/)
    expect(narration.textContent).not.toContain('adaptador nulo')
  })

  it('sin radio no ofrece buscar: lo explica antes de que se pulse', async () => {
    const fetchMock = stubBackend({
      ...EMPTY_ROUTES,
      [SYSTEM_ROUTE]: () => json(SYSTEM_WITHOUT_RADIO),
      [SCAN]: () => json([]),
    })
    render(<App />)
    // La limitacion ya se lee en la tarjeta de conexion, sin abrir nada.
    await screen.findByText('Ninguno registrado · el servidor no tiene Bluetooth')

    openDialog()

    const button = scanButton()
    expect(button).toHaveProperty('disabled', true)

    // Deshabilitado CON explicacion enlazada: quien navega con lector de
    // pantalla oye por que, no solo que no se puede.
    const noteId = button.getAttribute('aria-describedby')
    expect(noteId).not.toBeNull()
    const note = document.getElementById(noteId ?? '')
    expect(note?.textContent).toContain('no tiene acceso a Bluetooth')
    expect(note?.textContent).toContain('«null»')

    // Y no se finge ninguna busqueda: ni barra, ni peticion, ni "Buscando…".
    expect(screen.queryByRole('progressbar')).toBeNull()
    fireEvent.click(button)
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/devices/scan'),
      expect.anything(),
    )
    expect(screen.queryByText(/Buscando dispositivos/)).toBeNull()
  })

  it('mientras el escaneo dura, el progreso se ve y se anuncia', async () => {
    vi.useFakeTimers()
    let release = (): void => undefined
    const pending = new Promise<Response>((resolve) => {
      release = () => {
        resolve(json([NEAR]))
      }
    })
    stubBackend({
      ...EMPTY_ROUTES,
      [SYSTEM_ROUTE]: () => json(SYSTEM),
      [SCAN]: () => pending,
    })
    render(<App />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    openDialog()
    fireEvent.click(scanButton())

    // Anunciado, no solo dibujado: sin esto la espera es invisible para quien
    // no ve la barra.
    const status = screen.getByRole('status', { name: 'Estado del escaneo' })
    expect(status.textContent).toContain('puede tardar hasta 10 segundos')

    // Determinada: el maximo lo declara el servidor, asi que el indicador puede
    // responder "cuanto falta" en vez de limitarse a girar.
    const bar = screen.getByRole('progressbar', { name: 'Progreso del escaneo' })
    expect(bar.getAttribute('aria-valuemax')).toBe('10')
    expect(bar.getAttribute('aria-valuenow')).toBe('0')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
    expect(bar.getAttribute('aria-valuenow')).toBe('3')

    // Pasado el maximo anunciado, la barra deja de prometer un porcentaje: una
    // barra llena que sigue esperando mentiria.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000)
    })
    const overdue = screen.getByRole('progressbar', { name: 'Progreso del escaneo' })
    expect(overdue.getAttribute('aria-valuenow')).toBeNull()
    expect(status.textContent).toContain('tardando más')

    release()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MIN_VISIBLE_SCAN_MS)
    })

    expect(screen.getByText('1 dispositivo encontrado.')).toBeDefined()
    expect(screen.queryByRole('progressbar')).toBeNull()
    vi.useRealTimers()
  })

  it('anuncia el escaneo en curso y no deja lanzar dos a la vez', async () => {
    let release = (): void => undefined
    const pending = new Promise<Response>((resolve) => {
      release = () => {
        resolve(json([NEAR]))
      }
    })
    stubBackend({ ...EMPTY_ROUTES, [SCAN]: () => pending })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    // Un escaneo tarda segundos: sin esto la pantalla parece colgada.
    const status = screen.getByRole('status', { name: 'Estado del escaneo' })
    expect(status.getAttribute('aria-live')).toBe('polite')
    expect(status.textContent).toContain('puede tardar hasta 10 segundos')
    expect(scanButton()).toHaveProperty('disabled', true)

    release()
    await screen.findByText('1 dispositivo encontrado.')
  })

  it('si el servidor ya esta escaneando, lo dice y deshabilita el boton', async () => {
    stubBackend({
      ...EMPTY_ROUTES,
      [SCAN]: () => json({ detail: { code: 'device_busy', message: 'scan in progress' } }, 409),
    })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    // Mismo codigo que al conectar, significado distinto: aqui es el escaneo.
    expect(await screen.findByText(/Ya hay un escaneo en curso/)).toBeDefined()
    await waitFor(() => {
      expect(scanButton()).toHaveProperty('disabled', true)
    })
  })

  it('no promete una causa que el backend no da cuando el escaneo falla', async () => {
    stubBackend({
      ...EMPTY_ROUTES,
      [SCAN]: () => json({ detail: { code: 'device_write_failed', message: 'boom' } }, 502),
    })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    // 502 ya no incluye "sin Bluetooth": eso lo dice el 503 `device_unavailable`.
    const narration = await screen.findByText(/no pudo completar el escaneo/)
    expect(narration.textContent).toContain('expirara')
  })

  it('dice que el Bluetooth del servidor no esta disponible cuando responde 503', async () => {
    stubBackend({
      ...EMPTY_ROUTES,
      [SCAN]: () =>
        json(
          {
            detail: {
              code: 'device_unavailable',
              message: 'El Bluetooth de este equipo esta apagado: enciendelo y vuelve a buscar.',
            },
          },
          503,
        ),
    })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())

    expect(await screen.findByText(/no puede usar el Bluetooth/)).toBeDefined()
  })

  it('da de alta el dispositivo elegido y lo enlaza en un solo paso', async () => {
    const registered = { ...DEVICE, id: 'b2', name: 'LotusLantern', address: NEAR.address }
    let alta = false
    let enlace = false

    const fetchMock = stubBackend({
      [SCAN]: () => json([NEAR]),
      'GET /api/v1/devices': () => json(alta ? [{ ...registered, connected: enlace }] : []),
      // La version sube al enlazar, como hace el servidor: un estado con la
      // misma version se descarta por rancio, y con razon.
      'GET /api/v1/state': () =>
        json({
          ...STATE,
          version: enlace ? STATE.version + 1 : STATE.version,
          device: enlace ? { device_id: 'b2', connected: true, rssi: -45, last_error: null } : null,
        }),
      'POST /api/v1/devices': () => {
        alta = true
        return json(registered, 201)
      },
      'POST /api/v1/devices/b2/connect': () => {
        enlace = true
        return json({ ...registered, connected: true })
      },
    })
    render(<App />)
    await screen.findByText('Ninguno registrado')

    openDialog()
    fireEvent.click(scanButton())
    fireEvent.click(await screen.findByRole('button', { name: 'Registrar y conectar LotusLantern' }))

    // El alta y el enlace son dos llamadas del servidor, pero un solo gesto.
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/devices',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'LotusLantern', address: NEAR.address }),
        }),
      )
    })
    expect(await screen.findByText('LotusLantern · conectado')).toBeDefined()
    expect(screen.getByText('Enlazado')).toBeDefined()
    // Ya dado de alta: no se vuelve a ofrecer como si fuera nuevo.
    expect(screen.getByRole('button', { name: 'LotusLantern ya está dado de alta' })).toHaveProperty(
      'disabled',
      true,
    )
  })

  it('al conectar un segundo dispositivo explica que solo hay un enlace', async () => {
    const other = { ...DEVICE, id: 'b2', name: 'Tira del pasillo', connected: false }
    stubBackend({
      'GET /api/v1/devices': () => json([DEVICE, other]),
      'POST /api/v1/devices/b2/connect': () =>
        json({ detail: { code: 'device_busy', message: 'another device is linked' } }, 409),
    })
    render(<App />)
    await screen.findByText('Tira del salón · conectado')

    openDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Conectar Tira del pasillo' }))

    // El aviso se busca DENTRO del dialogo: es donde esta mirando quien acaba
    // de pulsar, y el de la pantalla de detras queda tapado por el modal (y
    // fuera del lector de pantalla, por `aria-modal`).
    const dialog = within(screen.getByRole('dialog', { name: 'Dispositivos' }))
    const alert = await dialog.findByRole('alert')
    expect(alert.textContent).toContain('Solo puede haber un dispositivo enlazado a la vez')
    // Y la salida esta a la vista: desconectar el que ocupa el enlace.
    expect(dialog.getByRole('button', { name: 'Desconectar Tira del salón' })).toBeDefined()
  })
})
