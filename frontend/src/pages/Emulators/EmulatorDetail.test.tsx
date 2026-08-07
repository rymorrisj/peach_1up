import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import EmulatorDetail from '@/pages/Emulators/EmulatorDetail';
import { apiFetch } from '@/api/client';
import type { components } from '@shared/types';

type CatalogEntry = components['schemas']['CatalogEntryResponse'];

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

function renderAt(slug: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/emulators/${slug}`]}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/emulators/:slug" element={<EmulatorDetail />} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const KNOWN_ENTRY: CatalogEntry = {
  slug: 'dosbox-x',
  name: 'DOSBox-X',
  version: '2024.07.01',
  description: 'DOS emulator, no ROM required.',
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

// Per dev_docs/v2/09_test_coverage.md-adjacent follow-up: locks in the actual
// catalog-miss branch (EmulatorDetail.tsx:164, `catalog.length > 0 && !entry`)
//, a non-empty catalog that simply doesn't contain the requested slug. This
// is distinct from the empty-catalog case already covered in
// routing.sectionRedirects.test.tsx ("/emulators/:slug still resolves to
// EmulatorDetail for a real (non-reserved) slug"), where catalog.length is 0
// and the page instead falls back to rendering the raw slug as its heading.
describe('EmulatorDetail, catalog-miss 404 UI', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows "Emulator not found." when the catalog is non-empty but has no matching slug', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (url === '/api/v1/emulator-items') return Promise.resolve([KNOWN_ENTRY]);
      if (typeof url === 'string' && url.startsWith('/api/v1/profile-items'))
        return Promise.resolve({ items: [] });
      return Promise.resolve([]);
    });

    renderAt('not-a-real-emulator');

    await waitFor(() => {
      expect(screen.getByText('Emulator not found.')).toBeInTheDocument();
    });
    // Confirms this is the catalog-miss branch, not the empty-catalog
    // fallback-heading case covered elsewhere, no raw-slug heading renders.
    expect(screen.queryByRole('heading', { name: 'not-a-real-emulator' })).not.toBeInTheDocument();
  });

  it('renders the normal detail page (not the 404 branch) when the slug matches a catalog entry', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (url === '/api/v1/emulator-items') return Promise.resolve([KNOWN_ENTRY]);
      if (typeof url === 'string' && url.startsWith('/api/v1/profile-items'))
        return Promise.resolve({ items: [] });
      return Promise.resolve([]);
    });

    renderAt('dosbox-x');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'DOSBox-X' })).toBeInTheDocument();
    });
    expect(screen.queryByText('Emulator not found.')).not.toBeInTheDocument();
  });
});
