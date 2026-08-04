import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import CollectionDetail from '@/pages/Software/CollectionDetail';
import { apiFetch } from '@/api/client';
import { createMockLibraryItem } from '@/test/helpers';

// Locks down the launch_commands sentinel logic in CollectionDetail.tsx
// (the local `launchCommands: string[] | null | undefined` state and its
// resolveLaunchCommands() function) ahead of a later extraction. Per the
// source comments there:
//   - undefined = not yet loaded (only true before the collection query
//     resolves; unreachable once the Save button is on screen, since the
//     same mount effect that clears the `!form` guard also seeds
//     launchCommands in the same commit)
//   - null = never configured / preserve — sent to the backend verbatim as
//     null, which enrich/PATCH treats as "field omitted" (exclude_none) and
//     leaves the stored value untouched
//   - [] = explicitly cleared — sent verbatim, persists as an empty list
//     (no auto-run)
// The point of resolveLaunchCommands is that an incidental save (editing an
// unrelated field, never touching the Advanced/commands UI) must resend
// whatever the current sentinel already is, not silently convert null to []
// or vice versa.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    rawDetail: unknown;
    constructor(status: number, detail: string, rawDetail?: unknown) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.rawDetail = rawDetail;
      this.name = 'ApiError';
    }
  },
}));

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
    genres: [],
    developer: null,
    publisher: null,
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

const adminUser = {
  id: 1,
  name: 'Admin',
  is_owner: true,
  is_admin: true,
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
};

interface Handler {
  match: string | RegExp;
  method?: string;
  respond: () => unknown;
}

interface RecordedCall {
  url: string;
  method: string;
  body: unknown;
}

function setupApi(handlers: Handler[] = []): RecordedCall[] {
  const allHandlers: Handler[] = [
    ...handlers,
    { match: '/api/v1/auth/me', respond: () => adminUser },
    { match: '/api/v1/auth/refresh', respond: () => ({ user: adminUser }) },
    {
      match: '/api/v1/settings/library-defaults',
      respond: () => ({ delete_media_on_removal: false, delete_original_on_upload: false }),
    },
    { match: '/api/v1/settings', respond: () => ({ metadata_provider: 'thegamesdb' }) },
    {
      match: /settings\/(thegamesdb-api-key\/status|igdb-status)/,
      respond: () => ({ enabled: true }),
    },
    { match: '/api/v1/user-items', respond: () => [] },
    { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [] }) },
    { match: '/api/v1/environment-items', respond: () => [] },
    { match: '/api/v1/tags', respond: () => [] },
    { match: /^\/api\/v1\/restrictions\//, respond: () => ({ restricted_user_item_ids: [] }) },
    { match: /\/launches$/, respond: () => [] },
  ];

  const calls: RecordedCall[] = [];

  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = typeof url === 'string' ? url : '';
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ url: u, method, body });
    for (const h of allHandlers) {
      const matches = typeof h.match === 'string' ? u === h.match : h.match.test(u);
      if (matches && (!h.method || h.method === method)) {
        return Promise.resolve().then(h.respond);
      }
    }
    return Promise.resolve([]);
  });

  return calls;
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

async function waitForLoaded() {
  await waitFor(() => {
    expect(screen.getAllByText('Doom')[0]).toBeInTheDocument();
  });
}

function callsTo(calls: RecordedCall[], url: string, method: string) {
  return calls.filter((c) => c.url === url && c.method === method);
}

async function saveAndWait(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => {
    expect(screen.getByText('Saved ✓')).toBeInTheDocument();
  });
}

function launchCommandsOf(body: unknown): string[] | null {
  return (body as { launch_commands: string[] | null }).launch_commands;
}

describe('CollectionDetail launch_commands sentinel', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('an incidental save does not flip a never-configured (null) value into an explicit empty list', async () => {
    const user = userEvent.setup();
    const calls = setupApi([
      {
        match: '/api/v1/game-item-bundle/by-slug/doom',
        method: 'GET',
        respond: () => fullCollection({ launch_commands: null }),
      },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ]);
    renderPage();
    await waitForLoaded();

    // Touch an unrelated field only — never open Advanced / the commands UI.
    await user.type(screen.getByLabelText('Publisher'), 'id Software');
    await saveAndWait(user);

    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH');
    expect(launchCommandsOf(patch[0].body)).toBeNull();
  });

  it('an incidental save does not flip an already-cleared ([]) value into null', async () => {
    const user = userEvent.setup();
    const calls = setupApi([
      {
        match: '/api/v1/game-item-bundle/by-slug/doom',
        method: 'GET',
        respond: () => fullCollection({ launch_commands: [] }),
      },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ]);
    renderPage();
    await waitForLoaded();

    await user.type(screen.getByLabelText('Publisher'), 'id Software');
    await saveAndWait(user);

    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH');
    expect(launchCommandsOf(patch[0].body)).toEqual([]);
  });

  it('explicitly clearing the last command sends an empty list, not null', async () => {
    const user = userEvent.setup();
    const calls = setupApi([
      {
        match: '/api/v1/game-item-bundle/by-slug/doom',
        method: 'GET',
        respond: () => fullCollection({ launch_commands: ['DOOM.EXE'] }),
      },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ]);
    renderPage();
    await waitForLoaded();

    await user.click(screen.getByRole('button', { name: 'Advanced' }));
    await user.click(screen.getByRole('button', { name: 'Remove command' }));

    await saveAndWait(user);

    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH');
    expect(launchCommandsOf(patch[0].body)).toEqual([]);
  });
});
