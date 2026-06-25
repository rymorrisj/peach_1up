/**
 * Acceptance test: Library page
 *
 * Renders the full page with all real child components.
 * Only the network boundary (apiFetch) is mocked.
 *
 * User flow: page loads with library items → user opens the Add Media modal
 * → modal is visible with the file drop/upload zone.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Library from '@/pages/Library'
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
          <Library />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('Library acceptance', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('shows library items then opens the Add Media modal on button click', async () => {
    const user = userEvent.setup()
    const items = [
      createMockLibraryItem({ id: 1, title: 'Doom', era: 'dos', slug: 'doom' }),
      createMockLibraryItem({ id: 2, title: 'Ultima VII', era: 'dos', slug: 'ultima-vii' }),
    ]
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/library/sets')) {
        return Promise.resolve([])
      }
      if (typeof url === 'string' && url.includes('/api/v1/library')) {
        return Promise.resolve(items)
      }
      return Promise.resolve([])
    })

    renderPage()

    // Primary content appears
    await waitFor(() => {
      // Title appears in both the art placeholder and the card label
      expect(screen.getAllByText('Doom').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Ultima VII').length).toBeGreaterThanOrEqual(1)
    })

    // User clicks the Add Media button
    await user.click(screen.getByRole('button', { name: /add media/i }))

    // The modal should be open and contain the drag-and-drop upload zone
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/drag and drop files here/i)).toBeInTheDocument()
    })
  })

  it('shows the empty state when the library has no items', async () => {
    vi.mocked(apiFetch).mockResolvedValue([])
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /your library is empty/i })).toBeInTheDocument()
    })
    // Add Media CTA inside the empty state is also present
    expect(screen.getAllByRole('button', { name: /add media/i }).length).toBeGreaterThanOrEqual(1)
  })
})
