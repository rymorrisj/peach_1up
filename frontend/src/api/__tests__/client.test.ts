import { api, ApiError, TimeoutError } from '@/api/client'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('api.fetch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns undefined for a 204 No Content response', async () => {
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const result = await api.fetch('/api/v1/test')
    expect(result).toBeUndefined()
  })

  it('throws ApiError with correct status and detail on a 4xx response', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await expect(api.fetch('/api/v1/test')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'Not found',
    })
  })

  it('throws ApiError on a 5xx response', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Server error' }), { status: 500 }),
    )
    await expect(api.fetch('/api/v1/test')).rejects.toBeInstanceOf(ApiError)
  })

  it('falls back to statusText when the body has no detail field', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 500, statusText: 'Internal Server Error' }),
    )
    await expect(api.fetch('/api/v1/test')).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
      detail: 'Internal Server Error',
    })
  })

  it('falls back to statusText when JSON parse fails', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new SyntaxError('not json')),
    })
    await expect(api.fetch('/api/v1/test')).rejects.toMatchObject({
      detail: 'Internal Server Error',
    })
  })

  it('includes Content-Type, X-Request-ID, and credentials: include on every request', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )
    await api.fetch('/api/v1/test')
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(headers['X-Request-ID']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    )
    expect(init.credentials).toBe('include')
  })
})

// ---------------------------------------------------------------------------
// Session / error event dispatch
//
// Note: the client does not navigate directly. On a session-ending response
// it dispatches a `session-expired` window event, which AppContext listens
// for and turns into a LOGOUT (clearing the user + showing the unauth modal).
// On other non-OK responses it dispatches an `api-error` event, which
// AppContext turns into a toast. Neither path calls a router directly.
// ---------------------------------------------------------------------------
describe('api.fetch session/error events', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('dispatches a session-expired event on a 401 response', async () => {
    const handler = vi.fn()
    window.addEventListener('session-expired', handler)
    try {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Not authenticated.' }), { status: 401 }),
      )
      await expect(api.fetch('/api/v1/library')).rejects.toBeInstanceOf(ApiError)
      expect(handler).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener('session-expired', handler)
    }
  })

  it('dispatches a session-expired event on a 403 response from an auth endpoint', async () => {
    const handler = vi.fn()
    window.addEventListener('session-expired', handler)
    try {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Forbidden' }), { status: 403 }),
      )
      await expect(api.fetch('/api/v1/auth/me')).rejects.toBeInstanceOf(ApiError)
      expect(handler).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener('session-expired', handler)
    }
  })

  it('dispatches an api-error toast event (not session-expired) on a 403 from a non-auth endpoint', async () => {
    const sessionHandler = vi.fn()
    const errorHandler = vi.fn()
    window.addEventListener('session-expired', sessionHandler)
    window.addEventListener('api-error', errorHandler)
    try {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Permission denied.' }), { status: 403 }),
      )
      await expect(api.fetch('/api/v1/library')).rejects.toBeInstanceOf(ApiError)
      expect(sessionHandler).not.toHaveBeenCalled()
      expect(errorHandler).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener('session-expired', sessionHandler)
      window.removeEventListener('api-error', errorHandler)
    }
  })

  it('dispatches an api-error toast event on a non-OK 500 response', async () => {
    const errorHandler = vi.fn()
    window.addEventListener('api-error', errorHandler)
    try {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Server error' }), { status: 500 }),
      )
      await expect(api.fetch('/api/v1/library')).rejects.toBeInstanceOf(ApiError)
      expect(errorHandler).toHaveBeenCalledTimes(1)
      const event = errorHandler.mock.calls[0][0] as CustomEvent<string>
      expect(event.detail).toBe('Server error')
    } finally {
      window.removeEventListener('api-error', errorHandler)
    }
  })
})

describe('api.fetch timeout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('throws TimeoutError when the request exceeds the abort timeout', async () => {
    mockFetch.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    )

    const promise = api.fetch('/api/v1/test')
    const assertion = expect(promise).rejects.toBeInstanceOf(TimeoutError)
    await vi.advanceTimersByTimeAsync(10_000)
    await assertion
  })
})
