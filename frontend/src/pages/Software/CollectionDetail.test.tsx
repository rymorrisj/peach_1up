import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import CollectionDetail from '@/pages/Software/CollectionDetail';
import { apiFetch, ApiError } from '@/api/client';
import { createMockLibraryItem } from '@/test/helpers';

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

// Minimal "fully populated" collection fixture. createMockLibraryItem's base
// object omits genres, CollectionDetail.tsx reads collection.genres.length
// with no null guard, so genres must always be overridden to avoid a crash.
function fullCollection(overrides?: Record<string, unknown>) {
  return createMockLibraryItem({
    id: 1,
    slug: 'doom',
    title: 'Doom',
    era: 'dos',
    launch_count: 5,
    launch_review_flagged: false,
    installed: true,
    requires_install: false,
    genres: ['Action', 'Shooter'],
    developer: 'id Software',
    publisher: 'id Software',
    content_rating: null,
    sort_title: null,
    description: null,
    category: null,
    year: 1993,
    delete_media_override: null,
    profile_item_id: null,
    last_launched_at: null,
    tags: [],
    ...overrides,
  });
}

function makeUser(overrides: Record<string, unknown>) {
  return {
    id: 2,
    name: 'Bob',
    is_owner: false,
    is_admin: false,
    pin_required: false,
    can_launch_media: true,
    can_manage_environment: false,
    can_manage_game: false,
    can_manage_media: false,
    can_manage_app: false,
    can_manage_controllerMapping: false,
    can_manage_settings: false,
    can_manage_users: false,
    block_unrated_media: false,
    is_locked: false,
    failed_pin_attempts: 0,
    ...overrides,
  };
}

const adminUser = makeUser({ id: 1, name: 'Admin', is_owner: true, is_admin: true });
const plainUser = makeUser({ id: 1, name: 'Player', is_owner: false, is_admin: false });

interface MockApiOptions {
  user?: unknown;
  collection?: unknown;
  collectionError?: InstanceType<typeof ApiError>;
  hangCollection?: boolean;
  users?: unknown[];
  launches?: unknown[];
  restrictions?: { restricted_user_item_ids: number[] };
}

function mockApi(opts: MockApiOptions) {
  vi.mocked(apiFetch).mockImplementation((url: unknown) => {
    if (typeof url !== 'string') return Promise.resolve([]);
    if (url === '/api/v1/auth/me') {
      return opts.user
        ? Promise.resolve(opts.user)
        : Promise.reject(new ApiError(401, 'Unauthenticated'));
    }
    if (url === '/api/v1/auth/refresh') {
      return Promise.resolve({ user: opts.user });
    }
    if (url.startsWith('/api/v1/game-item-bundle/by-slug/')) {
      if (opts.hangCollection) return new Promise(() => {});
      if (opts.collectionError) return Promise.reject(opts.collectionError);
      return Promise.resolve(opts.collection);
    }
    if (url.includes('/launches')) {
      return Promise.resolve(opts.launches ?? []);
    }
    if (url.startsWith('/api/v1/restrictions/game/')) {
      return Promise.resolve(opts.restrictions ?? { restricted_user_item_ids: [] });
    }
    if (url === '/api/v1/user-items') {
      return Promise.resolve(opts.users ?? []);
    }
    if (url.startsWith('/api/v1/profile-items')) {
      return Promise.resolve({ items: [] });
    }
    if (url.startsWith('/api/v1/environment-items')) {
      return Promise.resolve([]);
    }
    if (url === '/api/v1/settings/library-defaults') {
      return Promise.resolve({ delete_media_on_removal: false, delete_original_on_upload: false });
    }
    if (url === '/api/v1/settings') {
      return Promise.resolve({ metadata_provider: 'thegamesdb' });
    }
    if (
      url.includes('/settings/thegamesdb-api-key/status') ||
      url.includes('/settings/igdb-status')
    ) {
      return Promise.resolve({ enabled: true });
    }
    return Promise.resolve([]);
  });
}

function renderPage(slug = 'doom') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[`/software/games/${slug}`]}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <Routes>
              <Route path="/software/games/:slug" element={<CollectionDetail />} />
            </Routes>
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('CollectionDetail (read path)', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows a loading indicator while the collection is fetching', () => {
    mockApi({ user: plainUser, hangCollection: true });
    renderPage();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders a 404/not-found state when the collection query errors', async () => {
    mockApi({ user: plainUser, collectionError: new ApiError(404, 'Not found') });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/game not found/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: /back to software/i })).toBeInTheDocument();
  });

  it('renders a fully-populated collection for an admin/owner user', async () => {
    mockApi({ user: adminUser, collection: fullCollection() });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('Doom')[0]).toBeInTheDocument();
    });
    expect(screen.getAllByText(/id Software/)[0]).toBeInTheDocument();
    expect(screen.getByText(/Action, Shooter/)).toBeInTheDocument();
  });

  it('renders the restrictions section and fetches from /api/v1/restrictions/game/{id} when isAdminOrOwner is true', async () => {
    mockApi({
      user: adminUser,
      collection: fullCollection(),
      users: [makeUser({ id: 2, name: 'Bob', is_owner: false })],
      restrictions: { restricted_user_item_ids: [2] },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /restrictions/i })).toBeInTheDocument();
      expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeChecked();
    });

    const calledUrls = vi.mocked(apiFetch).mock.calls.map((c) => c[0]);
    expect(calledUrls).toContain('/api/v1/restrictions/game/1');
  });

  it('does not render the restrictions section or fetch restrictions when isAdminOrOwner is false', async () => {
    mockApi({ user: plainUser, collection: fullCollection() });
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('Doom')[0]).toBeInTheDocument();
    });
    expect(screen.queryByRole('heading', { name: /restrictions/i })).not.toBeInTheDocument();

    const calledUrls = vi.mocked(apiFetch).mock.calls.map((c) => c[0]);
    expect(
      calledUrls.some((u) => typeof u === 'string' && u.includes('/api/v1/restrictions')),
    ).toBe(false);
  });

  it('renders launch history when session history entries are present', async () => {
    mockApi({
      user: plainUser,
      collection: fullCollection(),
      launches: [
        {
          id: 1,
          started_at: '2026-01-01T10:00:00Z',
          ended_at: '2026-01-01T10:00:05Z',
          emulator_slug: 'dosbox-x',
          sandboxed: true,
          exit_code: 0,
          error_message: null,
        },
      ],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Session History')).toBeInTheDocument();
    });
    expect(screen.getByText('dosbox-x')).toBeInTheDocument();
    expect(screen.getByText('sandboxed')).toBeInTheDocument();
  });

  it('renders empty states for users, profiles, platforms, restrictions, and launch history with no crash', async () => {
    mockApi({
      user: adminUser,
      collection: fullCollection(),
      users: [],
      launches: [],
      restrictions: { restricted_user_item_ids: [] },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /restrictions/i })).toBeInTheDocument();
    });
    expect(screen.getByText(/no sub-accounts/i)).toBeInTheDocument();
    expect(screen.queryByText('Session History')).not.toBeInTheDocument();
  });
});
