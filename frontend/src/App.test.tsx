import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('muestra el estado del backend cuando /api/v1/health responde', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    render(<App />)

    expect(await screen.findByText(/Conectado — status: ok/)).toBeDefined()
  })

  it('muestra el fallo sin romper la pagina cuando el backend no responde', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))

    render(<App />)

    expect(await screen.findByText(/Sin conexión/)).toBeDefined()
  })
})
