/**
 * Cliente HTTP del backend.
 *
 * La base es relativa a proposito: el mismo bundle funciona servido por FastAPI
 * en :8000 y detras del proxy de Vite en :5173. Eso elimina la necesidad de una
 * URL de backend horneada y de CORS.
 */
export const API_BASE_URL = '/api/v1'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface HealthStatus {
  status: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: 'application/json' },
    ...init,
  })

  if (!response.ok) {
    throw new ApiError(response.status, `${init?.method ?? 'GET'} ${path} -> ${response.status}`)
  }

  return (await response.json()) as T
}

// Los tipos de Device, RGBColor y DeviceCapabilities se declararan en
// src/domain/ cuando el backend fije su contrato (Fase 2). Declararlos ahora
// obligaria a inventar valores que el README no especifica.
export const apiClient = {
  getHealth: (): Promise<HealthStatus> => request<HealthStatus>('/health'),
}
