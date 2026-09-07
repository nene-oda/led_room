import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DeviceStatus } from './DeviceStatus'
import type { DeviceView } from '../../state/lightStateContext'

const DEVICE: DeviceView = {
  id: 'a1',
  name: 'Tira del salón',
  address: 'AA:BB:CC:DD:EE:FF',
  connected: true,
  rssi: -50,
  lastError: null,
}

describe('DeviceStatus', () => {
  it('muestra las tres señales por separado, no un unico indicador', () => {
    render(
      <DeviceStatus
        backend="reachable"
        realtime="reconnecting"
        device={{ ...DEVICE, connected: false }}
        radio="unknown"
        linkPending={false}
        onConnect={vi.fn()}
        onDisconnect={vi.fn()}
      />,
    )

    // Un WebSocket caido y un dispositivo desconectado son fallos distintos y
    // se leen por separado, aunque el servidor HTTP siga respondiendo.
    expect(screen.getByText('Responde')).toBeDefined()
    expect(screen.getByText('Reconectando…')).toBeDefined()
    expect(screen.getByText('Tira del salón · desconectado')).toBeDefined()
  })

  it('anuncia los cambios de conexion en una region viva', () => {
    render(
      <DeviceStatus
        backend="checking"
        realtime="connecting"
        device={null}
        radio="unknown"
        linkPending={false}
        onConnect={vi.fn()}
        onDisconnect={vi.fn()}
      />,
    )

    expect(screen.getByRole('status').getAttribute('aria-live')).toBe('polite')
    expect(screen.getByText('Ninguno registrado')).toBeDefined()
  })

  it('cuando el servidor no tiene radio lo dice en la senal del dispositivo', () => {
    render(
      <DeviceStatus
        backend="reachable"
        realtime="open"
        device={null}
        radio="missing"
        linkPending={false}
        onConnect={vi.fn()}
        onDisconnect={vi.fn()}
      />,
    )

    // "Ninguno registrado" a secas invita a ir a buscar uno; con un servidor
    // sin radio ese viaje no lleva a ninguna parte, y se dice aqui.
    expect(screen.getByText('Ninguno registrado · el servidor no tiene Bluetooth')).toBeDefined()
  })

  it('ofrece conectar cuando hay dispositivo y no hay enlace', () => {
    const onConnect = vi.fn()
    render(
      <DeviceStatus
        backend="reachable"
        realtime="open"
        device={{ ...DEVICE, connected: false }}
        radio="unknown"
        linkPending={false}
        onConnect={onConnect}
        onDisconnect={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Conectar' }))

    expect(onConnect).toHaveBeenCalled()
  })

  it('muestra el ultimo fallo del enlace en vez de esconderlo', () => {
    render(
      <DeviceStatus
        backend="reachable"
        realtime="open"
        device={{ ...DEVICE, connected: false, lastError: 'Timeout al conectar' }}
        radio="unknown"
        linkPending={false}
        onConnect={vi.fn()}
        onDisconnect={vi.fn()}
      />,
    )

    expect(screen.getByText(/Timeout al conectar/)).toBeDefined()
  })
})
