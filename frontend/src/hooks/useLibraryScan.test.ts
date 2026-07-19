import React from 'react'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
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
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(AppProvider, null, children),
    )
}

// Route apiFetch by endpoint instead of call order. AppProvider fires
// /auth/me -> /auth/refresh on mount and the hook fires /api/v1/jobs on mount
// (hydrating a finished scan's preview from the job list); positional
// mockResolvedValueOnce queues are consumed by those calls before a test's
// target call ever runs, which silently desyncs every subsequent response.
// Routing by URL is immune to that ordering.
type ApiHandler = (url: string, opts?: RequestInit) => unknown

let apiRoutes: Record<string, ApiHandler>

function setApiRoutes(overrides: Record<string, ApiHandler> = {}) {
  apiRoutes = {
    // AppProvider mount noise
    '/api/v1/auth/me': () => ({ id: 1, username: 'tester' }),
    '/api/v1/auth/refresh': () => ({ user: { id: 1, username: 'tester' } }),
    // Hook mount hydration reads the job list for a finished scan's preview
    // (scan/status itself is now stateless) — idle by default so it is a no-op.
    '/api/v1/jobs': () => [],
    '/api/v1/game-items/scan/status': () => ({ running: false, error: null }),
    ...overrides,
  }
}

const DONE_JOB = {
  id: 'job-1',
  kind: 'scan',
  status: 'done',
  progress: 1,
  message: 'Scan complete — 1 item(s) ready to import.',
  result: {
    preview: [
      { title: 'Game', file_path: '/lib/game.nes', detected_era: 'nes', is_loose: true, is_zip: false },
    ],
  },
}

describe('useLibraryScan', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setApiRoutes()
    // A thrown handler becomes a rejected promise (for failure-path tests).
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) =>
      Promise.resolve().then(() => {
        const handler = apiRoutes[url]
        return handler ? handler(url, opts) : undefined
      }),
    )
  })
  afterEach(() => vi.useRealTimers())

  it('handleScan triggers a POST to the scan endpoint', async () => {
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported: vi.fn() }),
      { wrapper: createWrapper() },
    )

    await act(async () => { result.current.handleScan() })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/game-items/scan',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('polling stops and preview is populated when scan finishes', async () => {
    vi.useFakeTimers()

    // The hook no longer polls /scan/status or fetches /api/v1/jobs/{id}.
    // Completion now flows entirely through AppContext's own 1500ms poll of
    // the list endpoint GET /api/v1/jobs, which only starts once handleScan's
    // onSuccess registers job-1 in state.backgroundJobs via UPSERT_JOB (status
    // 'processing'). The hook's own mount-time hydration read (the `open`
    // effect) also hits this same URL, before the scan is even triggered, so
    // the queue below serves that call an empty list first and only reports
    // the finished job on the poll tick that follows registration.
    const jobsSeq: unknown[] = [[], [DONE_JOB]]
    setApiRoutes({
      '/api/v1/game-items/scan': () => ({ started: true, directory: '/lib', job_id: 'job-1' }),
      '/api/v1/jobs': () => jobsSeq.shift() ?? [DONE_JOB],
    })

    const onImported = vi.fn()
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported }),
      { wrapper: createWrapper() },
    )

    // Flush mutation onSuccess — two act rounds drain TanStack's scheduler.
    // This also registers job-1 in state.backgroundJobs, which is what starts
    // AppContext's poll effect (it only runs while an active job exists).
    await act(async () => { result.current.handleScan() })
    await act(async () => {})

    expect(result.current.scanning).toBe(true)

    // AppContext's poll tick (1500ms) fetches the job list again and reports
    // job-1 as done with its preview result.
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })

    expect(result.current.scanning).toBe(false)
    expect(result.current.status?.preview).toHaveLength(1)
    // onImported is NOT called at scan end — only called after Phase 2 import
    expect(onImported).not.toHaveBeenCalled()
  })

  it('handleImport posts selected paths and calls onImported when items are imported', async () => {
    const IMPORT_RESULT = { imported: 1, skipped: 0, errors: [] }
    setApiRoutes({ '/api/v1/game-items/scan/import': () => IMPORT_RESULT })

    const onImported = vi.fn()
    const { result } = renderHook(
      () => useLibraryScan({ open: true, onImported }),
      { wrapper: createWrapper() },
    )

    await act(async () => {
      await result.current.handleImport(['/lib/game.nes'])
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/game-items/scan/import',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(onImported).toHaveBeenCalledOnce()
    expect(result.current.importResult).toEqual(IMPORT_RESULT)
    expect(result.current.importing).toBe(false)
  })

  it('handleImport does not call onImported when imported count is zero', async () => {
    const IMPORT_RESULT = { imported: 0, skipped: 2, errors: [] }
    setApiRoutes({ '/api/v1/game-items/scan/import': () => IMPORT_RESULT })

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

  it('a stale in-flight import does not clobber a later successful import after Escape-closing and reopening the modal', async () => {
    // Regression test for a race where the modal's native <dialog> Escape-key
    // close bypasses the disabled Cancel button and does not cancel the
    // in-flight import request. If the user then reopens the modal and runs
    // a second, successful import, the first (now-stale) request's eventual
    // failure must not resurrect the error banner over the fresh success.
    let resolveFirst!: (v: unknown) => void
    const firstImportPromise = new Promise((resolve) => { resolveFirst = resolve })
    let callCount = 0
    setApiRoutes({
      '/api/v1/game-items/scan/import': () => {
        callCount += 1
        // First call: stays pending until we manually settle it later.
        // Second call: resolves immediately with a successful result.
        return callCount === 1 ? firstImportPromise : { imported: 1, skipped: 0, errors: [] }
      },
    })

    const onImported = vi.fn()
    const { result, rerender } = renderHook(
      ({ open }: { open: boolean }) => useLibraryScan({ open, onImported }),
      { wrapper: createWrapper(), initialProps: { open: true } },
    )

    // Start the first (slow) import — mirrors clicking Import.
    let firstImportDone!: Promise<void>
    act(() => {
      firstImportDone = result.current.handleImport(['/lib/game1.nes'])
    })
    expect(result.current.importing).toBe(true)

    // User presses Escape mid-request: the dialog closes natively (open ->
    // false) without cancelling the request above, then the modal is
    // reopened.
    await act(async () => { rerender({ open: false }) })
    await act(async () => { rerender({ open: true }) })

    expect(result.current.importing).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.importResult).toBeNull()

    // A second, fresh import now runs and succeeds.
    await act(async () => {
      await result.current.handleImport(['/lib/game2.nes'])
    })
    expect(result.current.importResult).toEqual({ imported: 1, skipped: 0, errors: [] })
    expect(result.current.error).toBeNull()

    // The original (first) request finally settles — as a failure — well
    // after the second one already succeeded.
    await act(async () => {
      resolveFirst(Promise.reject(new ApiError(500, 'boom')))
      await firstImportDone
    })

    // The stale failure must not resurrect the error banner over the
    // already-successful, current import result.
    expect(result.current.error).toBeNull()
    expect(result.current.importResult).toEqual({ imported: 1, skipped: 0, errors: [] })
  })

  it('error state is set when the scan POST fails', async () => {
    setApiRoutes({
      '/api/v1/game-items/scan': () => { throw new ApiError(503, 'Scan failed') },
    })

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
