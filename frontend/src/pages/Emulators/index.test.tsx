import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import Emulators from '@/pages/Emulators/Emulators';
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <Emulators />
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const DOSBOX_ENTRY: CatalogEntry = {
  slug: 'dosbox',
  name: 'DOSBox-X',
  version: '2024.07.01',
  description: 'Accurate DOS and early-Windows emulator.',
  license: 'GPL-2.0',
  install_type: 'zip',
  required: false,
  is_installed: true,
  install_path: 'C:\\emulators\\dosbox-x\\dosbox-x.exe',
  supported_formats: ['exe', 'com', 'bat'],
  container_enabled: true,
  container_hardcap_disabled: false,
  skip_cpu_limit: false,
  skip_memory_limit: false,
  known_limitations: [],
};

const PCSX2_ENTRY: CatalogEntry = {
  slug: 'pcsx2',
  name: 'PCSX2',
  version: '1.7.5',
  description: 'PlayStation 2 emulator.',
  license: 'GPL-3.0',
  install_type: 'bundled',
  required: false,
  is_installed: false,
  install_path: null,
  supported_formats: ['iso', 'chd'],
  container_enabled: false,
  container_hardcap_disabled: false,
  skip_cpu_limit: false,
  skip_memory_limit: false,
  known_limitations: [],
};

describe('Emulators page', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows a loading indicator while the catalog is fetching', () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders emulator cards after a successful API response', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulator-items')) {
        return Promise.resolve([DOSBOX_ENTRY, PCSX2_ENTRY]);
      }
      return Promise.resolve([]);
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('DOSBox-X')).toBeInTheDocument();
      expect(screen.getByText('PCSX2')).toBeInTheDocument();
    });
  });

  it('shows the empty state when the catalog is empty', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulator-items')) {
        return Promise.resolve([]);
      }
      return Promise.resolve([]);
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/no emulators found/i)).toBeInTheDocument();
    });
  });

  it('shows how many emulators are ready', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/emulator-items')) {
        return Promise.resolve([DOSBOX_ENTRY, PCSX2_ENTRY]);
      }
      return Promise.resolve([]);
    });
    renderPage();
    await waitFor(() => {
      // "1 of 2 ready", only DOSBox-X is installed
      expect(screen.getByText(/1 of 2 ready/i)).toBeInTheDocument();
    });
  });
});
