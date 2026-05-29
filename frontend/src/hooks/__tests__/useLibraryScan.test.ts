import React from 'react'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useLibraryScan } from '@/hooks/useLibraryScan'
import { apiFetch, ApiError } from '@/api/client'

vi.mock('@/api/client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/api/client')>()
  return { ...mod, apiFetch: vi.fn() }
})

const mockApiFetch = vi.mocked(apiFetch)

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children)
}

const DONE_STATUS = {
  running: false,
  progress: 1,
  total: 1,
  results: [{ folder_path: '/lib/game', name: 'Game', executable_path: null }],
}

describe('useLibraryScan', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.useRealTimers())

  it('handleScan triggers a POST to the scan endpoint', async () => {
    mockApiFetch
      .mockResolvedValueOnce(undefined)   // POST /scan
      .mockResolvedValue(DONE_STATUS)     // GET /scan/status

    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported: vi.fn() }),
      { wrapper: createWrapper() },
    )

    await act(async () => { result.current.handleScan() })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/scan',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('polling stops and onImported is called when status.running is false', async () => {
    vi.useFakeTimers()

    const RUNNING_STATUS = { running: true, progress: 0, total: 1, results: [] }

    mockApiFetch
      .mockResolvedValueOnce(undefined)       // POST /scan
      .mockResolvedValueOnce(RUNNING_STATUS)  // first poll — still running
      .mockResolvedValueOnce(DONE_STATUS)     // second poll — done

    const onImported = vi.fn()
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported }),
      { wrapper: createWrapper() },
    )

    // Flush mutation onSuccess so the interval is registered
    await act(async () => { result.current.handleScan() })
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/v1/library/scan',
        expect.objectContaining({ method: 'POST' }),
      ),
    )

    // First poll tick — still running; advance and drain async callback
    await vi.advanceTimersByTimeAsync(1000)
    // Second poll tick — done; advance and drain async callback
    await vi.advanceTimersByTimeAsync(1000)

    expect(result.current.scanning).toBe(false)
    expect(onImported).toHaveBeenCalledOnce()
  })

  it('error state is set when the scan POST fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(503, 'Scan failed'))

    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported: vi.fn() }),
      { wrapper: createWrapper() },
    )

    await act(async () => { result.current.handleScan() })

    await waitFor(() => expect(result.current.error).toBe('Scan failed'))
    expect(result.current.scanning).toBe(false)
  })
})
