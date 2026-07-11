import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

// GET /api/v1/bios returns Page[BiosRequirement] (dev_docs/v2/08, Task 3).
function biosPage(items: BiosRequirement[], overrides: Partial<{ total: number; limit: number; offset: number }> = {}) {
  return { items, total: overrides.total ?? items.length, limit: overrides.limit ?? 50, offset: overrides.offset ?? 0 }
}

describe('Bios tab (/emulators/bios) — list-only, no detail route', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders the cross-emulator BIOS list', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        return Promise.resolve(biosPage([PS1_BIOS]))
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
        return Promise.resolve(biosPage([PS1_BIOS]))
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
        return Promise.resolve(biosPage([PS1_BIOS]))
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('PS1 BIOS')).toBeInTheDocument())
    // No row exposes an internal navigation link (e.g. to /emulators/... or
    // /bios/...) that would imply a :slug detail route. GuidanceNote's external
    // "Download" link (rel="noreferrer" target="_blank", href to a third-party
    // BIOS source) is a legitimate per-row guidance link, not a detail
    // affordance, so it's intentionally excluded from this ban.
    const internalLinks = screen.queryAllByRole('link').filter((link) => {
      const href = link.getAttribute('href') ?? ''
      return href.startsWith('/emulators') || href.startsWith('/bios')
    })
    expect(internalLinks).toHaveLength(0)
  })

  it('shows the empty state when no emulator in the catalog requires a BIOS', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        return Promise.resolve(biosPage([]))
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no bios requirements/i)).toBeInTheDocument()
    })
  })

  it('renders pagination controls and pages forward when total exceeds one page', async () => {
    const PAGE_2_BIOS: BiosRequirement = { ...PS1_BIOS, slug: 'ps2-bios', name: 'PS2 BIOS' }
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/bios')) {
        const offset = new URL(url, 'http://localhost').searchParams.get('offset')
        if (offset === '1') {
          return Promise.resolve(biosPage([PAGE_2_BIOS], { total: 2, limit: 1, offset: 1 }))
        }
        return Promise.resolve(biosPage([PS1_BIOS], { total: 2, limit: 1, offset: 0 }))
      }
      return Promise.resolve([])
    })
    renderPage()

    await waitFor(() => expect(screen.getByText('PS1 BIOS')).toBeInTheDocument())
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => expect(screen.getByText('PS2 BIOS')).toBeInTheDocument())
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
  })
})
