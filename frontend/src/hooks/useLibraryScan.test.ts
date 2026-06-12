import React from 'react'
import { renderHook, act } from '@testing-library/react'
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

const RUNNING_STATUS = { running: true, preview: [], error: null }

const DONE_STATUS = {
  running: false,
  preview: [
    { title: 'Game', media_path: '/lib/game.nes', detected_era: 'nes', is_loose: true, is_zip: false },
  ],
  error: null,
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

  it('polling stops and preview is populated when scan finishes', async () => {
    vi.useFakeTimers()

    mockApiFetch
      .mockResolvedValueOnce(undefined)       // POST /scan
      .mockResolvedValueOnce(RUNNING_STATUS)  // first poll — still running
      .mockResolvedValueOnce(DONE_STATUS)     // second poll — done

    const onImported = vi.fn()
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported }),
      { wrapper: createWrapper() },
    )

    // Flush mutation onSuccess — two act rounds drain TanStack's scheduler
    await act(async () => { result.current.handleScan() })
    await act(async () => {})

    // First poll tick — still running
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    // Second poll tick — done
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })

    expect(result.current.scanning).toBe(false)
    expect(result.current.status?.preview).toHaveLength(1)
    // onImported is NOT called at scan end — only called after Phase 2 import
    expect(onImported).not.toHaveBeenCalled()
  })

  it('handleImport posts selected paths and calls onImported when items are imported', async () => {
    const IMPORT_RESULT = { imported: 1, skipped: 0, errors: [] }
    mockApiFetch.mockResolvedValueOnce(IMPORT_RESULT)

    const onImported = vi.fn()
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported }),
      { wrapper: createWrapper() },
    )

    await act(async () => {
      await result.current.handleImport(['/lib/game.nes'])
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/scan/import',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(onImported).toHaveBeenCalledOnce()
    expect(result.current.importResult).toEqual(IMPORT_RESULT)
    expect(result.current.importing).toBe(false)
  })

  it('handleImport does not call onImported when imported count is zero', async () => {
    const IMPORT_RESULT = { imported: 0, skipped: 2, errors: [] }
    mockApiFetch.mockResolvedValueOnce(IMPORT_RESULT)

    const onImported = vi.fn()
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported }),
      { wrapper: createWrapper() },
    )

    await act(async () => {
      await result.current.handleImport(['/lib/game1.nes', '/lib/game2.nes'])
    })

    expect(onImported).not.toHaveBeenCalled()
    expect(result.current.importResult?.skipped).toBe(2)
  })

  it('error state is set when the scan POST fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(503, 'Scan failed'))

    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported: vi.fn() }),
      { wrapper: createWrapper() },
    )

    // Two act rounds to drain TanStack's mutation rejection through onError
    await act(async () => { result.current.handleScan() })
    await act(async () => {})

    expect(result.current.error).toBe('Scan failed')
    expect(result.current.scanning).toBe(false)
  })
})
