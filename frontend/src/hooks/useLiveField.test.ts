import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useLiveField } from './useLiveField'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

function setup() {
  const send = vi.fn<(value: number) => void>()
  const persist = vi.fn<(value: number) => void>()
  const { result, unmount } = renderHook(() =>
    useLiveField<number>({ send, persist, intervalMs: 50, settleMs: 300 }),
  )
  return { send, persist, result, unmount }
}

describe('useLiveField', () => {
  it('el arrastre sale por el canal rapido y no persiste nada mientras dura', () => {
    const { send, persist, result } = setup()

    act(() => {
      result.current.update(10)
      vi.advanceTimersByTime(60)
      result.current.update(20)
      vi.advanceTimersByTime(60)
    })

    expect(send.mock.calls).toEqual([[10], [20]])
    expect(persist).not.toHaveBeenCalled()
  })

  it('un gesto que termina sin avisar se persiste igualmente al quedarse quieto', () => {
    const { persist, result } = setup()

    act(() => {
      result.current.update(70)
      vi.advanceTimersByTime(300)
    })

    // Sin esto, mover el brillo y soltar dejaria el valor aplicado pero no
    // guardado: se perderia al reiniciar el servidor.
    expect(persist).toHaveBeenCalledExactlyOnceWith(70)
  })

  it('un cierre explicito persiste al momento y cancela el commit de reserva', () => {
    const { persist, result } = setup()

    act(() => {
      result.current.update(70)
      result.current.commit(75)
      vi.advanceTimersByTime(1000)
    })

    expect(persist).toHaveBeenCalledExactlyOnceWith(75)
  })

  it('no persiste despues de desmontar', () => {
    const { persist, result, unmount } = setup()

    act(() => {
      result.current.update(70)
    })
    unmount()
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(persist).not.toHaveBeenCalled()
  })
})
