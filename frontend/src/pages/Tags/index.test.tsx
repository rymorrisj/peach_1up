import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Tags from '@/pages/Tags'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

type TagRead = components['schemas']['TagRead']

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  setSessionToken: vi.fn(),
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
          <Tags />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const SAMPLE_TAGS: TagRead[] = [
  { id: 1, name: 'cozy-evening', color: 'coral', item_count: 4 },
  { id: 2, name: 'classic', color: 'amber', item_count: 12 },
]

describe('Tags page', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('shows a loading indicator while tags are fetching', () => {
    // Never resolves so the loading state persists
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByText(/loading tags/i)).toBeInTheDocument()
  })

  it('renders user tags after a successful API response', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.startsWith('/api/v1/tags')) {
        return Promise.resolve(SAMPLE_TAGS)
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      // Tag name appears in both the row label and the preview pill
      expect(screen.getAllByText('cozy-evening').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('classic').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('shows the empty-state message when no user tags exist', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.startsWith('/api/v1/tags')) {
        return Promise.resolve([])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no user tags yet/i)).toBeInTheDocument()
    })
  })

  it('always renders the system tags section', async () => {
    vi.mocked(apiFetch).mockResolvedValue([])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('System tags')).toBeInTheDocument()
    })
  })
})
