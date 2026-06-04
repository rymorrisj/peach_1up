import { apiFetch, ApiError, setSessionToken } from '@/api/client'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('apiFetch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setSessionToken(null)
  })

  it('returns undefined for a 204 No Content response', async () => {
    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const result = await apiFetch('/api/v1/test')
    expect(result).toBeUndefined()
  })

  it('throws ApiError with correct status and detail on a 4xx response', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Not found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await expect(apiFetch('/api/v1/test')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'Not found',
    })
  })

  it('throws ApiError on a 5xx response', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Server error' }), { status: 500 }),
    )
    await expect(apiFetch('/api/v1/test')).rejects.toBeInstanceOf(ApiError)
  })

  it('falls back to statusText when the body has no detail field', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 500, statusText: 'Internal Server Error' }),
    )
    await expect(apiFetch('/api/v1/test')).rejects.toMatchObject({
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
    await expect(apiFetch('/api/v1/test')).rejects.toMatchObject({
      detail: 'Internal Server Error',
    })
  })

  it('includes Content-Type and X-Request-ID headers on every request', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )
    await apiFetch('/api/v1/test')
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(headers['X-Request-ID']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    )
  })
})
