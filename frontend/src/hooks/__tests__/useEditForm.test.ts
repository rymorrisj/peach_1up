import React from 'react'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEditForm } from '@/hooks/useEditForm'
import { apiFetch, ApiError } from '@/api/client'
import { createMockLibraryItem } from '@/test/helpers'

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

describe('useEditForm', () => {
  beforeEach(() => vi.clearAllMocks())

  it('form is hydrated from the item on mount', async () => {
    const item = createMockLibraryItem({
      title: 'Doom',
      publisher: 'id Software',
      year: 1993,
      era: 'dos',
    })

    const { result } = renderHook(
      () => useEditForm({ item, slug: 'doom' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.form).not.toBeNull())

    expect(result.current.form?.title).toBe('Doom')
    expect(result.current.form?.publisher).toBe('id Software')
    expect(result.current.form?.year).toBe('1993')
    expect(result.current.form?.era).toBe('dos')
  })

  it('setField updates only the targeted field', async () => {
    const item = createMockLibraryItem({ title: 'Original', publisher: 'Acme', era: 'dos' })

    const { result } = renderHook(
      () => useEditForm({ item, slug: 'item' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.form).not.toBeNull())

    act(() => { result.current.setField('title', 'Updated') })

    expect(result.current.form?.title).toBe('Updated')
    expect(result.current.form?.publisher).toBe('Acme')
    expect(result.current.form?.era).toBe('dos')
  })

  it('handleSave calls PATCH on the correct URL with the form payload', async () => {
    mockApiFetch.mockResolvedValueOnce(undefined)

    const item = createMockLibraryItem({ id: 5, title: 'Test', era: 'dos' })

    const { result } = renderHook(
      () => useEditForm({ item, slug: 'test' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.form).not.toBeNull())

    await act(async () => { result.current.handleSave() })

    await waitFor(() => expect(result.current.saveSuccess).toBe(true))

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/library/5',
      expect.objectContaining({ method: 'PATCH' }),
    )

    const body = JSON.parse(
      (mockApiFetch.mock.calls[0][1] as RequestInit).body as string,
    )
    expect(body.title).toBe('Test')
    expect(body.era).toBe('dos')
  })

  it('saveError is populated with the API error detail on failure', async () => {
    mockApiFetch.mockRejectedValueOnce(new ApiError(500, 'Internal Server Error'))

    const item = createMockLibraryItem({ id: 5 })

    const { result } = renderHook(
      () => useEditForm({ item, slug: 'test' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.form).not.toBeNull())

    await act(async () => { result.current.handleSave() })

    await waitFor(() => expect(result.current.saveError).toBe('Internal Server Error'))
    expect(result.current.saveSuccess).toBe(false)
  })
})
