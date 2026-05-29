import { renderHook } from '@testing-library/react'
import { useConfirmToken } from '@/hooks/useConfirmToken'
import { apiFetch, ApiError } from '@/api/client'

vi.mock('@/api/client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/api/client')>()
  return { ...mod, apiFetch: vi.fn() }
})

const mockApiFetch = vi.mocked(apiFetch)

describe('useConfirmToken', () => {
  beforeEach(() => vi.clearAllMocks())

  it('issue() POSTs to the confirm-delete URL and returns the token', async () => {
    mockApiFetch.mockResolvedValueOnce({ confirmation_token: 'tok-abc123' })

    const { result } = renderHook(() => useConfirmToken())
    const token = await result.current.issue('/api/v1/library/1/confirm-delete')

    expect(token).toBe('tok-abc123')
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/1/confirm-delete',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('consume() sends DELETE with the token as a query param', async () => {
    mockApiFetch.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useConfirmToken())
    await result.current.consume('/api/v1/library/1', 'tok-abc123')

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/1?confirmation_token=tok-abc123',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('error from issue() propagates to the caller', async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(403, 'Forbidden'))

    const { result } = renderHook(() => useConfirmToken())

    await expect(
      result.current.issue('/api/v1/library/1/confirm-delete'),
    ).rejects.toMatchObject({ name: 'ApiError', status: 403, detail: 'Forbidden' })
  })
})
