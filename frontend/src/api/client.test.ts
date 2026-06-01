import { apiFetch, ApiError, setSessionToken } from '@/api/client'

describe('apiFetch', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    setSessionToken(null)
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  function mockFetch(status: number, body?: unknown, statusText = '') {
    const ok = status >= 200 && status < 300
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok,
      status,
      statusText,
      json: () =>
        body !== undefined
          ? Promise.resolve(body)
          : Promise.reject(new SyntaxError('no body')),
    })
  }

  it('returns undefined for 204', async () => {
    mockFetch(204)
    const result = await apiFetch('/test')
    expect(result).toBeUndefined()
  })

  it('throws ApiError on 4xx', async () => {
    mockFetch(404, { detail: 'Not found' }, 'Not Found')
    await expect(apiFetch('/test')).rejects.toBeInstanceOf(ApiError)
  })

  it('throws ApiError on 5xx', async () => {
    mockFetch(500, { detail: 'Server error' }, 'Internal Server Error')
    await expect(apiFetch('/test')).rejects.toBeInstanceOf(ApiError)
  })

  it('extracts detail from JSON error body', async () => {
    mockFetch(400, { detail: 'Validation failed' }, 'Bad Request')
    await expect(apiFetch('/test')).rejects.toMatchObject({
      status: 400,
      detail: 'Validation failed',
    })
  })

  it('falls back to statusText when body has no detail field', async () => {
    mockFetch(403, { message: 'no detail key here' }, 'Forbidden')
    await expect(apiFetch('/test')).rejects.toMatchObject({
      detail: 'Forbidden',
    })
  })

  it('falls back to statusText when JSON parse fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: () => Promise.reject(new SyntaxError('not json')),
    })
    await expect(apiFetch('/test')).rejects.toMatchObject({
      detail: 'Internal Server Error',
    })
  })

  it('includes X-Request-ID on every request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data: 'ok' }),
    })
    globalThis.fetch = fetchMock
    await apiFetch('/test')
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers['X-Request-ID']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    )
  })
})
