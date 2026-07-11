import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Bios from '@/pages/Emulators/Bios'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

type BiosRequirement = components['schemas']['BiosRequirement']

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: () => 'test-csrf-token',
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
    <MemoryRouter initialEntries={['/emulators/bios']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Bios />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const PS1_BIOS: BiosRequirement = {
  slug: 'ps1-bios',
  name: 'PS1 BIOS',
  platform: 'ps1',
  bios_path: 'emulators/duckstation/bios',
  guidance_text: 'Place your PS1 BIOS file.',
  guidance_url: 'https://example.invalid',
  is_present: false,
  required: true,
}

describe('Bios tab (/emulators/bios) — list-only, no detail route', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders the cross-emulator BIOS list', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        return Promise.resolve([PS1_BIOS])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('PS1 BIOS')).toBeInTheDocument()
    })
  })

  it('hosts the live BiosPlaceAction component on each row (dev_docs 08, decision 10)', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        return Promise.resolve([PS1_BIOS])
      }
      return Promise.resolve([])
    })
    renderPage()
    // BiosPlaceAction renders this action button only for slugs it supports
    // (ps1-bios is one) — its presence proves Bios.tsx actually mounts the
    // real, already-live component rather than a stub.
    await waitFor(() => {
      expect(screen.getByText(/Locate file\/folder/)).toBeInTheDocument()
    })
  })

  it('renders no per-item detail affordance — this is a list-only tab', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        return Promise.resolve([PS1_BIOS])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('PS1 BIOS')).toBeInTheDocument())
    // No row is a navigable link/button that would imply a :slug detail route —
    // the only interactive control per row is the place action itself.
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('shows the empty state when no emulator in the catalog requires a BIOS', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        return Promise.resolve([])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no bios requirements/i)).toBeInTheDocument()
    })
  })
})
