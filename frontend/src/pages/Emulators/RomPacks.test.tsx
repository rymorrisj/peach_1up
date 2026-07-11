import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import RomPacks from '@/pages/Emulators/RomPacks'
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
    <MemoryRouter initialEntries={['/emulators/rom-packs']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <RomPacks />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const ROM_PACK_ENTRY: CatalogEntry = {
  slug: '86box-roms',
  name: '86Box ROM Pack',
  version: '1.0.0',
  description: 'ROM pack for 86Box.',
  license: 'Custom',
  install_type: 'rom_pack',
  required: true,
  is_installed: false,
  install_path: null,
  supported_formats: [],
  container_enabled: false,
  container_hardcap_disabled: false,
  skip_cpu_limit: false,
  skip_memory_limit: false,
  known_limitations: [],
}

const NON_ROM_PACK_ENTRY: CatalogEntry = {
  slug: 'dosbox-x',
  name: 'DOSBox-X',
  version: '2024.07.01',
  description: 'DOS emulator, no ROM pack.',
  license: 'GPL-2.0',
  install_type: 'zip',
  required: false,
  is_installed: true,
  install_path: 'C:\\emulators\\dosbox-x\\dosbox-x.exe',
  supported_formats: ['exe'],
  container_enabled: true,
  container_hardcap_disabled: false,
  skip_cpu_limit: false,
  skip_memory_limit: false,
  known_limitations: [],
}

describe('ROM Packs tab (/emulators/rom-packs) — list-only, no detail route', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders only catalog entries whose install_type is rom_pack', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulators')) {
        return Promise.resolve([ROM_PACK_ENTRY, NON_ROM_PACK_ENTRY])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('86Box ROM Pack')).toBeInTheDocument()
    })
    expect(screen.queryByText('DOSBox-X')).not.toBeInTheDocument()
  })

  it('hosts the live CloneRomPackButton component on each row (dev_docs 08, decision 10)', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulators')) {
        return Promise.resolve([ROM_PACK_ENTRY])
      }
      return Promise.resolve([])
    })
    renderPage()
    // CloneRomPackButton renders "Clone ROM Pack" when the pack is not
    // installed — its presence proves RomPacks.tsx mounts the real,
    // already-live component rather than a stub.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /clone rom pack/i })).toBeInTheDocument()
    })
  })

  it('renders no per-item navigable link — this is a list-only tab', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulators')) {
        return Promise.resolve([ROM_PACK_ENTRY])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('86Box ROM Pack')).toBeInTheDocument())
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('shows the empty state when no emulator in the catalog requires a ROM pack', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulators')) {
        return Promise.resolve([NON_ROM_PACK_ENTRY])
      }
      return Promise.resolve([])
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no rom packs/i)).toBeInTheDocument()
    })
  })
})
