/**
 * Acceptance test: Emulators page
 *
 * Renders the full page with all real child components.
 * Only the network boundary (apiFetch) is mocked.
 *
 * User flow: page loads → emulator cards appear → user clicks "Auto-detect"
 * → page remains stable (no crash, cards still visible).
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Emulators from '@/pages/Emulators/Emulators'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

type CatalogEntry = components['schemas']['CatalogEntryResponse']

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
          <Emulators />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const CATALOG: CatalogEntry[] = [
  {
    slug: 'dosbox',
    name: 'DOSBox-X',
    version: '2024.07.01',
    description: 'Accurate DOS and early-Windows emulator.',
    license: 'GPL-2.0',
    install_type: 'zip',
    required: false,
    is_installed: true,
    install_path: 'C:\\emulators\\dosbox-x\\dosbox-x.exe',
    supported_formats: ['exe', 'com'],
    container_enabled: true,
    container_hardcap_disabled: false,
    skip_cpu_limit: false,
    skip_memory_limit: false,
    known_limitations: [],
  },
  {
    slug: 'duckstation',
    name: 'DuckStation',
    version: '0.1.9999',
    description: 'PlayStation 1 emulator.',
    license: 'GPL-3.0',
    install_type: 'zip',
    required: false,
    is_installed: false,
    install_path: null,
    supported_formats: ['cue', 'chd'],
    container_enabled: false,
    container_hardcap_disabled: false,
    skip_cpu_limit: false,
    skip_memory_limit: false,
    known_limitations: [],
  },
]

describe('Emulators acceptance', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('loads emulator cards and the Auto-detect button remains functional', async () => {
    const user = userEvent.setup()
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulators')) {
        return Promise.resolve(CATALOG)
      }
      return Promise.resolve([])
    })

    renderPage()

    // Primary content appears after load
    await waitFor(() => {
      expect(screen.getByText('DOSBox-X')).toBeInTheDocument()
      expect(screen.getByText('DuckStation')).toBeInTheDocument()
    })

    // User clicks Auto-detect — this invalidates the query; no crash expected
    const autoDetectBtn = screen.getByRole('button', { name: /auto-detect/i })
    await user.click(autoDetectBtn)

    // Cards should still be present after the action
    expect(screen.getByText('DOSBox-X')).toBeInTheDocument()
  })
})
