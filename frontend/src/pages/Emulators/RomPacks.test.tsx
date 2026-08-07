import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import RomPacks from '@/pages/Emulators/RomPacks';
import { apiFetch } from '@/api/client';
import type { components } from '@shared/types';

type CatalogEntry = components['schemas']['CatalogEntryResponse'];
type RomPackItem = components['schemas']['RomPackItemRead'];

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.name = 'ApiError';
    }
  },
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/emulators/rom-packs']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <RomPacks />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
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
};

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
};

// GET /api/v1/emulator-items/rom-packs returns Page[RomPackItemRead]
// (dev_docs/v2/08, Task 4), items are cross-referenced against the
// (still bare-list) /api/v1/emulator-items catalog by slug for the
// is_installed/guidance fields CloneRomPackButton/GuidanceNote need.
function romPackItemFor(entry: CatalogEntry): RomPackItem {
  return {
    id: null,
    slug: entry.slug,
    name: entry.name,
    emulator_slug: '',
    install_path: entry.install_path,
    source_url: null,
    is_present: entry.is_installed,
    installed_at: null,
    notes: null,
    created_at: null,
    updated_at: null,
  };
}

function romPacksPage(
  items: RomPackItem[],
  overrides: Partial<{ total: number; limit: number; offset: number }> = {},
) {
  return {
    items,
    total: overrides.total ?? items.length,
    limit: overrides.limit ?? 50,
    offset: overrides.offset ?? 0,
  };
}

/** Mocks both consumed endpoints; the more specific /rom-packs path must be
 * checked before the catalog path since it is a substring match. */
function mockRomPacksApi(
  catalog: CatalogEntry[],
  romPackPageByOffset?: (offset: string | null) => ReturnType<typeof romPacksPage>,
) {
  const defaultPage = romPacksPage(
    catalog.filter((e) => e.install_type === 'rom_pack').map(romPackItemFor),
  );
  vi.mocked(apiFetch).mockImplementation((url) => {
    if (typeof url !== 'string') return Promise.resolve([]);
    if (url.includes('/api/v1/emulator-items/rom-packs')) {
      if (romPackPageByOffset) {
        const offset = new URL(url, 'http://localhost').searchParams.get('offset');
        return Promise.resolve(romPackPageByOffset(offset));
      }
      return Promise.resolve(defaultPage);
    }
    if (url.includes('/api/v1/emulator-items')) return Promise.resolve(catalog);
    return Promise.resolve([]);
  });
}

describe('ROM Packs tab (/emulators/rom-packs), list-only, no detail route', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders only catalog entries whose install_type is rom_pack', async () => {
    mockRomPacksApi([ROM_PACK_ENTRY, NON_ROM_PACK_ENTRY]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('86Box ROM Pack')).toBeInTheDocument();
    });
    expect(screen.queryByText('DOSBox-X')).not.toBeInTheDocument();
  });

  it('hosts the live CloneRomPackButton component on each row (dev_docs 08, decision 10)', async () => {
    mockRomPacksApi([ROM_PACK_ENTRY]);
    renderPage();
    // CloneRomPackButton renders "Clone ROM Pack" when the pack is not
    // installed, its presence proves RomPacks.tsx mounts the real,
    // already-live component rather than a stub.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /clone rom pack/i })).toBeInTheDocument();
    });
  });

  it('renders no per-item navigable link, this is a list-only tab', async () => {
    mockRomPacksApi([ROM_PACK_ENTRY]);
    renderPage();
    await waitFor(() => expect(screen.getByText('86Box ROM Pack')).toBeInTheDocument());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows the empty state when no emulator in the catalog requires a ROM pack', async () => {
    mockRomPacksApi([NON_ROM_PACK_ENTRY]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/no rom packs/i)).toBeInTheDocument();
    });
  });

  it('renders pagination controls and pages forward when total exceeds one page', async () => {
    const SECOND_ROM_PACK_ENTRY: CatalogEntry = {
      ...ROM_PACK_ENTRY,
      slug: 'ps2-bios-pack',
      name: 'PS2 BIOS Pack',
    };
    const catalog = [ROM_PACK_ENTRY, SECOND_ROM_PACK_ENTRY];
    mockRomPacksApi(catalog, (offset) =>
      offset === '1'
        ? romPacksPage([romPackItemFor(SECOND_ROM_PACK_ENTRY)], { total: 2, limit: 1, offset: 1 })
        : romPacksPage([romPackItemFor(ROM_PACK_ENTRY)], { total: 2, limit: 1, offset: 0 }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText('86Box ROM Pack')).toBeInTheDocument());
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => expect(screen.getByText('PS2 BIOS Pack')).toBeInTheDocument());
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
  });
});
