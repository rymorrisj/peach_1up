import { renderHook, act } from '@testing-library/react'
import { useConfirmToken } from '@/hooks/useConfirmToken'

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    detail: string
    constructor(status: number, detail: string) {
      super(detail)
      this.status = status
      this.detail = detail
      this.name = 'ApiError'
    }
  },
}))

import { apiFetch, ApiError } from '@/api/client'

describe('useConfirmToken', () => {
  const mockApiFetch = vi.mocked(apiFetch)

  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it('issue() POSTs to the confirm-delete URL and returns the token', async () => {
    mockApiFetch.mockResolvedValueOnce({ confirmation_token: 'tok-abc123' })

    const { result } = renderHook(() => useConfirmToken())

    let token!: string
    await act(async () => {
      token = await result.current.issue('/api/v1/library/1/confirm-delete')
    })

    expect(token).toBe('tok-abc123')
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/1/confirm-delete',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('consume() sends DELETE with the token as a query param', async () => {
    mockApiFetch.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useConfirmToken())

    await act(async () => {
      await result.current.consume('/api/v1/library/1', 'tok-abc123')
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/1?confirmation_token=tok-abc123',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('error from issue() propagates to the caller', async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(403, 'Forbidden'))

    const { result } = renderHook(() => useConfirmToken())

    await expect(
      act(async () => {
        await result.current.issue('/api/v1/library/1/confirm-delete')
      }),
    ).rejects.toMatchObject({ name: 'ApiError', status: 403, detail: 'Forbidden' })
  })

  it('issue → consume → DELETE fires with token in query string', async () => {
    mockApiFetch
      .mockResolvedValueOnce({ confirmation_token: 'tok123' })
      .mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useConfirmToken())

    let token!: string
    await act(async () => {
      token = await result.current.issue('/api/v1/library/1/confirm-delete')
    })

    expect(token).toBe('tok123')

    await act(async () => {
      await result.current.consume('/api/v1/library/1', token)
    })

    expect(mockApiFetch).toHaveBeenLastCalledWith(
      '/api/v1/library/1?confirmation_token=tok123',
      { method: 'DELETE' },
    )
  })

  it('issue → cancel (no consume) → DELETE does not fire', async () => {
    mockApiFetch.mockResolvedValueOnce({ confirmation_token: 'tok456' })

    const { result } = renderHook(() => useConfirmToken())

    await act(async () => {
      await result.current.issue('/api/v1/library/1/confirm-delete')
    })

    const deleteCalls = mockApiFetch.mock.calls.filter(
      ([, init]) => (init as RequestInit)?.method === 'DELETE',
    )
    expect(deleteCalls).toHaveLength(0)
  })

  it('rapid re-issue does not reject', async () => {
    mockApiFetch.mockResolvedValue({ confirmation_token: 'tokX' })

    const { result } = renderHook(() => useConfirmToken())

    await act(async () => {
      await Promise.all([
        result.current.issue('/api/v1/library/1/confirm-delete'),
        result.current.issue('/api/v1/library/2/confirm-delete'),
        result.current.issue('/api/v1/library/3/confirm-delete'),
      ])
    })

    expect(mockApiFetch).toHaveBeenCalledTimes(3)
    expect(mockApiFetch.mock.calls.every(([, init]) => (init as RequestInit)?.method === 'POST')).toBe(true)
  })
})
