import { useEffect, useState } from 'react'

import { apiClient } from './api/client'

/**
 * Union discriminada en vez de varios booleanos: fija el patron con el que se
 * modelara despues el estado del dispositivo (disconnected / connecting /
 * connected / error).
 */
type BackendState =
  | { kind: 'loading' }
  | { kind: 'ok'; status: string }
  | { kind: 'error'; message: string }

export function App() {
  const [state, setState] = useState<BackendState>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false

    apiClient
      .getHealth()
      .then((health) => {
        if (!cancelled) setState({ kind: 'ok', status: health.status })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            kind: 'error',
            message: error instanceof Error ? error.message : 'Error desconocido',
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="app">
      <h1>LED Room</h1>
      <section aria-labelledby="backend-heading">
        <h2 id="backend-heading">Backend</h2>
        <p className={`status status--${state.kind}`} role="status" aria-live="polite">
          {state.kind === 'loading' && 'Comprobando /api/v1/health…'}
          {state.kind === 'ok' && `Conectado — status: ${state.status}`}
          {state.kind === 'error' && `Sin conexión — ${state.message}`}
        </p>
      </section>
    </main>
  )
}
