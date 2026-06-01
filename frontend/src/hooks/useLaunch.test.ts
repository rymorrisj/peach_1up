import React from 'react'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useLaunch } from '@/hooks/useLaunch'

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch, ApiError } from '@/api/client'

let qc: QueryClient

function Wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe('useLaunch', () => {
  const mockApiFetch = vi.mocked(apiFetch)

  beforeEach(() => {
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    vi.useFakeTimers()
    mockApiFetch.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('success path: launch → launchSuccess → poll sees ended_at → onSettled called', async () => {
    mockApiFetch
      .mockResolvedValueOnce({ launch_history_id: 42, warnings: ['disk low'] })
      .mockResolvedValueOnce({ ended_at: null })
      .mockResolvedValueOnce({ ended_at: '2024-01-01T00:00:00Z' })

    const onSettled = vi.fn()
    const { result } = renderHook(
      () => useLaunch({ targetId: 1, targetType: 'library', onSettled }),
      { wrapper: Wrapper },
    )

    await act(async () => {
      result.current.launch(5)
    })

    await waitFor(() => expect(result.current.launchSuccess).toBe(true))
    expect(result.current.launchWarnings).toEqual(['disk low'])

    await act(async () => {
      vi.advanceTimersByTime(2000)
    })

    await act(async () => {
      vi.advanceTimersByTime(2000)
    })

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1))
    expect(result.current.isLaunching).toBe(false)
  })

  it('error path: API error surfaces in error field', async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(500, 'Launch failed on server'))

    const { result } = renderHook(
      () => useLaunch({ targetId: 1, targetType: 'library' }),
      { wrapper: Wrapper },
    )

    await act(async () => {
      result.current.launch(5)
    })

    await waitFor(() => expect(result.current.error).toBe('Launch failed on server'))
    expect(result.current.isLaunching).toBe(false)
  })

  it('stop() calls stop endpoint and ends polling', async () => {
    mockApiFetch
      .mockResolvedValueOnce({ launch_history_id: 99, warnings: [] })
      .mockResolvedValueOnce(undefined)

    const { result } = renderHook(
      () => useLaunch({ targetId: 1, targetType: 'library' }),
      { wrapper: Wrapper },
    )

    await act(async () => {
      result.current.launch(5)
    })
    await waitFor(() => expect(result.current.launchSuccess).toBe(true))

    await act(async () => {
      await result.current.stop()
    })

    expect(result.current.isLaunching).toBe(false)
    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/launches/99/stop', { method: 'POST' })
  })

  it('interval is cleared on unmount', async () => {
    mockApiFetch.mockResolvedValueOnce({ launch_history_id: 7, warnings: [] })

    const { result, unmount } = renderHook(
      () => useLaunch({ targetId: 1, targetType: 'library' }),
      { wrapper: Wrapper },
    )

    await act(async () => {
      result.current.launch(5)
    })
    await waitFor(() => expect(result.current.launchSuccess).toBe(true))

    const callsBefore = mockApiFetch.mock.calls.length
    unmount()

    await act(async () => {
      vi.advanceTimersByTime(8000)
    })

    expect(mockApiFetch.mock.calls.length).toBe(callsBefore)
  })
})
