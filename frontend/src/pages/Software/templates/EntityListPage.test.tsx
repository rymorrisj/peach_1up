import { screen, waitFor, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import { apiFetch } from '@/api/client';
import { EntityListPage } from './EntityListPage';
import { appDomainConfig } from '../configs/appConfig';

// Basic smoke coverage: renders without throwing, plus a targeted check on
// the bundleApiPath(String(entity.id)) call in handleRemove, a real edit to
// App/Media's rendered path that was previously only verified by hand-tracing
// during the CollectionDetail composition phase. Not exhaustive behavior
// coverage (pagination, empty state, etc. are out of scope for this pass).
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

function minimalApp(overrides?: Record<string, unknown>) {
  return {
    id: 42,
    slug: 'my-app',
    title: 'My App',
    description: null,
    tags: [],
    is_pc: true,
    category: null,
    publisher: null,
    developer: null,
    year: null,
    installed: false,
    environment_item_id: null,
    profile_item_id: null,
    launch_disk_id: 100,
    display_disk_id: 100,
    last_launched_at: null,
    launch_count: 0,
    items: [
      {
        id: 100,
        app_item_bundle_id: 42,
        file_path: '/apps/myapp.exe',
        executable_path: null,
        cover_art_path: null,
        cover_art_url: null,
      },
    ],
    ...overrides,
  };
}

interface RecordedCall {
  url: string;
  method: string;
}

function mockApi(entities: unknown[]): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = typeof url === 'string' ? url : '';
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ url: u, method });
    if (u.startsWith('/api/v1/app-items')) {
      return Promise.resolve({ items: entities, total: entities.length, limit: 50, offset: 0 });
    }
    if (u === '/api/v1/settings/library-defaults') {
      return Promise.resolve({ delete_media_on_removal: false, delete_original_on_upload: false });
    }
    // App's real backend requires a confirmation_token on delete (see
    // appConfig.tsx's deleteConfig comment), so removal is a two-step
    // issue-then-consume flow, not a plain DELETE.
    if (method === 'POST' && u.endsWith('/confirm-delete')) {
      return Promise.resolve({ confirmation_token: 'test-confirmation-token' });
    }
    if (method === 'DELETE' && u.startsWith('/api/v1/app-item-bundle/')) {
      return Promise.resolve(undefined);
    }
    return Promise.resolve([]);
  });
  return calls;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <EntityListPage config={appDomainConfig} />
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('EntityListPage', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders without throwing given a minimal entity list', async () => {
    mockApi([minimalApp()]);
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('My App').length).toBeGreaterThan(0);
    });
  });

  it('constructs the delete URL from bundleApiPath(String(entity.id)) with the issued confirmation token', async () => {
    const user = userEvent.setup();
    const calls = mockApi([minimalApp()]);
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('My App').length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: 'Remove My App' }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      const issued = calls.find((c) => c.method === 'POST' && c.url.endsWith('/confirm-delete'));
      expect(issued?.url).toBe('/api/v1/app-item-bundle/42/confirm-delete');
      const del = calls.find((c) => c.method === 'DELETE');
      expect(del?.url).toBe(
        '/api/v1/app-item-bundle/42?confirmation_token=test-confirmation-token',
      );
    });
  });
});
