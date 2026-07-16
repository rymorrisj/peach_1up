import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Games from '@/pages/Software/Games'
import { apiFetch } from '@/api/client'
import { createMockLibraryItem } from '@/test/helpers'

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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Games />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('Software page', () => {
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
      if (typeof url === 'string' && url.includes('/api/v1/game-items')) {
        return Promise.resolve({ items, total: items.length, limit: 50, offset: 0 })
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
      if (typeof url === 'string' && url.includes('/api/v1/game-items')) {
        return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 })
      }
      return Promise.resolve([])
    })
    renderPage()
    // Post-EntityListPage-cutover copy: EntityListPage's generic empty state
    // is "No {entityLabelPlural} yet" (see templates/EntityListPage.tsx),
    // replacing the old bespoke Games.tsx-only "Your software library is
    // empty" heading.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /no games yet/i })).toBeInTheDocument()
    })
  })

  it('renders the "+ Add game" button', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    renderPage()
    // Post-EntityListPage-cutover copy: the TopBar add button label is now
    // generic "+ Add {entityLabel}" (see templates/EntityListPage.tsx),
    // replacing the old bespoke Games.tsx-only "+ Add Media" label.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add game/i })).toBeInTheDocument()
    })
  })
})
