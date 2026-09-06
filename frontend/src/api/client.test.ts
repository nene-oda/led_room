import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiClient } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiClient.getHealth', () => {
  it('consulta la ruta relativa /api/v1/health', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiClient.getHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', expect.anything())
  })

  it('lanza ApiError con el codigo cuando el backend responde con error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))

    await expect(apiClient.getHealth()).rejects.toBeInstanceOf(ApiError)
  })
})
