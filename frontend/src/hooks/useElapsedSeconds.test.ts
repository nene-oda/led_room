import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useElapsedSeconds } from './useElapsedSeconds'

afterEach(() => {
  vi.useRealTimers()
})

describe('useElapsedSeconds', () => {
  it('cuenta segundos completos mientras esta activo', async () => {
    vi.useFakeTimers()
    const { result } = renderHook(({ active }) => useElapsedSeconds(active), {
      initialProps: { active: true },
    })

    expect(result.current).toBe(0)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    expect(result.current).toBe(3)
  })

  it('vuelve a cero al pararse, para que el siguiente arranque empiece limpio', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ active }) => useElapsedSeconds(active), {
      initialProps: { active: true },
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(result.current).toBe(5)

    // Sin este reinicio, el segundo escaneo pintaria un fotograma con la barra
    // a medias antes de empezar de verdad.
    act(() => {
      rerender({ active: false })
    })

    expect(result.current).toBe(0)
  })

  it('deja de contar cuando se para: no sigue un temporizador huerfano', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ active }) => useElapsedSeconds(active), {
      initialProps: { active: true },
    })

    act(() => {
      rerender({ active: false })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(result.current).toBe(0)
  })
})
