import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Library from '@/pages/Library'
import { apiFetch } from '@/api/client'
import { createMockLibraryItem } from '@/test/helpers'
import type { components } from '@shared/types'

type ProfileRead = components['schemas']['ProfileRead']

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  setSessionToken: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, public readonly detail: string) {
      super(detail)
      this.name = 'ApiError'
    }
  },
}))

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Library />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const PROFILE: ProfileRead = {
  id: 1,
  name: 'DOSBox Default',
  slug: 'dosbox-default',
  emulator_slug: 'dosbox',
  era: 'dos',
  is_bundled: true,
  enable_networking: false,
  enable_dgvoodoo2: false,
  use_drive: false,
  item_count: 2,
  total_launches: 10,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('Library page', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('shows a loading indicator while library items are fetching', () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('renders library item titles after a successful API response', async () => {
    const items = [
      createMockLibraryItem({ id: 1, title: 'Doom', era: 'dos', slug: 'doom' }),
      createMockLibraryItem({ id: 2, title: 'Quake', era: 'dos', slug: 'quake' }),
    ]
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/library')) {
        return Promise.resolve(items)
      }
      if (typeof url === 'string' && url.includes('/api/v1/profiles')) {
        return Promise.resolve([PROFILE])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      // Title appears in both the art placeholder and the card label
      expect(screen.getAllByText('Doom').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Quake').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders the empty state when the library is empty', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/library')) {
        return Promise.resolve([])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /your library is empty/i })).toBeInTheDocument()
    })
  })

  it('renders the "+ Add Media" button', async () => {
    vi.mocked(apiFetch).mockResolvedValue([])
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add media/i })).toBeInTheDocument()
    })
  })
})
