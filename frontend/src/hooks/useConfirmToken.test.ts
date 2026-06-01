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
    }
  },
  setSessionToken: vi.fn(),
}))

import { apiFetch } from '@/api/client'

describe('useConfirmToken', () => {
  const mockApiFetch = vi.mocked(apiFetch)

  beforeEach(() => {
    mockApiFetch.mockReset()
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
