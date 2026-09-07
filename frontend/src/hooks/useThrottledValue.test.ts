import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useThrottledValue } from './useThrottledValue'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useThrottledValue', () => {
  it('con 200 movimientos en 1 s emite como mucho 21 veces y el ultimo valor siempre', () => {
    const emit = vi.fn<(value: number) => void>()
    const { result } = renderHook(() => useThrottledValue(emit, 50))

    act(() => {
      // Un arrastre real: ~200 eventos de puntero repartidos en un segundo.
      for (let i = 1; i <= 200; i += 1) {
        result.current(i)
        vi.advanceTimersByTime(5)
      }
      // Se deja correr el borde de salida.
      vi.advanceTimersByTime(50)
    })

    expect(emit.mock.calls.length).toBeLessThanOrEqual(21)
    expect(emit.mock.calls.length).toBeGreaterThan(1)
    expect(emit).toHaveBeenLastCalledWith(200)
  })

  it('emite el primer valor sin esperar (borde de entrada)', () => {
    const emit = vi.fn<(value: number) => void>()
    const { result } = renderHook(() => useThrottledValue(emit, 50))

    act(() => {
      result.current(7)
    })

    expect(emit).toHaveBeenCalledExactlyOnceWith(7)
  })

  it('descarta los valores intermedios: gana el ultimo, no se encolan', () => {
    const emit = vi.fn<(value: number) => void>()
    const { result } = renderHook(() => useThrottledValue(emit, 50))

    act(() => {
      result.current(1)
      result.current(2)
      result.current(3)
      vi.advanceTimersByTime(50)
    })

    expect(emit.mock.calls).toEqual([[1], [3]])
  })

  it('no emite despues de desmontar', () => {
    const emit = vi.fn<(value: number) => void>()
    const { result, unmount } = renderHook(() => useThrottledValue(emit, 50))

    act(() => {
      result.current(1)
      result.current(2)
    })
    unmount()
    act(() => {
      vi.advanceTimersByTime(200)
    })

    expect(emit.mock.calls).toEqual([[1]])
  })
})
