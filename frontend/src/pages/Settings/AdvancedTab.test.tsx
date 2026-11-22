import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import AdvancedTab from '@/pages/Settings/AdvancedTab';
import { apiFetch } from '@/api/client';
import { METADATA_FETCH_DISCLAIMER } from '@/lib/metadataFetch';

// Covers the "Enable metadata fetching" toggle on the Metadata Provider card:
// turning it on asks for confirmation (Cancel leaves it off), turning it off
// applies at once, the hint icon shows only while on, and only the owner can
// change it. apiFetch is mocked at the network boundary, as in the
// CollectionDetail.*.test.tsx files.
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

const ownerUser = makeUser({ id: 1, name: 'Owner', is_owner: true, is_admin: true });
const settingsManager = makeUser({ can_manage_settings: true });

interface RecordedCall {
  url: string;
  method: string;
  body: unknown;
}

function setupApi(user: unknown, settings: Record<string, unknown>): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = typeof url === 'string' ? url : '';
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ url: u, method, body });
    if (u === '/api/v1/auth/me') return Promise.resolve(user);
    if (u === '/api/v1/auth/refresh') return Promise.resolve({ user });
    // AppProvider's bootstrap job-list fetch; SET_JOBS needs an array.
    if (u === '/api/v1/jobs') return Promise.resolve([]);
    if (u === '/api/v1/settings' && method === 'GET') return Promise.resolve(settings);
    if (u === '/api/v1/settings' && method === 'PATCH') return Promise.resolve({ updated: [] });
    if (/settings\/(thegamesdb-api-key\/status|igdb-status|pin-pepper\/status)/.test(u)) {
      return Promise.resolve({ enabled: false });
    }
    return Promise.resolve({});
  });
  return calls;
}

function patchCalls(calls: RecordedCall[]) {
  return calls.filter((c) => c.url === '/api/v1/settings' && c.method === 'PATCH');
}

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AppProvider>
          <AdvancedTab />
        </AppProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

async function findToggle() {
  const toggle = await screen.findByRole('checkbox', { name: 'Enable metadata fetching' });
  return toggle;
}

describe('AdvancedTab, metadata fetching toggle', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders the toggle off by default with no hint icon', async () => {
    setupApi(ownerUser, { metadata_provider: 'thegamesdb' });
    renderTab();

    const toggle = await findToggle();
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).not.toBeChecked();
    expect(
      screen.queryByRole('button', { name: 'About metadata fetching' }),
    ).not.toBeInTheDocument();
  });

  it('does not show the old accuracy line', async () => {
    setupApi(ownerUser, { metadata_provider: 'thegamesdb' });
    renderTab();

    await findToggle();
    expect(screen.queryByText(/may be incomplete or inaccurate/)).not.toBeInTheDocument();
  });

  it('turning on opens the confirm modal, and Cancel leaves it off', async () => {
    const user = userEvent.setup();
    const calls = setupApi(ownerUser, { metadata_provider: 'thegamesdb' });
    renderTab();

    const toggle = await findToggle();
    await waitFor(() => expect(toggle).toBeEnabled());
    await user.click(toggle);

    const dialog = await screen.findByRole('dialog', { name: 'Enable metadata fetching' });
    expect(dialog).toHaveTextContent(METADATA_FETCH_DISCLAIMER);

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(toggle).not.toBeChecked();
    expect(patchCalls(calls)).toEqual([]);
  });

  it('Confirm in the modal saves the setting as true', async () => {
    const user = userEvent.setup();
    const calls = setupApi(ownerUser, { metadata_provider: 'thegamesdb' });
    renderTab();

    const toggle = await findToggle();
    await waitFor(() => expect(toggle).toBeEnabled());
    await user.click(toggle);
    await screen.findByRole('dialog', { name: 'Enable metadata fetching' });
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(patchCalls(calls).map((c) => c.body)).toEqual([
      { updates: { metadata_fetch_enabled: true } },
    ]);
  });

  it('when on, shows the hint icon and turning off saves at once with no modal', async () => {
    const user = userEvent.setup();
    const calls = setupApi(ownerUser, {
      metadata_provider: 'thegamesdb',
      metadata_fetch_enabled: true,
    });
    renderTab();

    const toggle = await findToggle();
    await waitFor(() => expect(toggle).toBeChecked());
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(screen.getByRole('button', { name: 'About metadata fetching' })).toBeInTheDocument();

    await user.click(toggle);

    await waitFor(() => {
      expect(patchCalls(calls).map((c) => c.body)).toEqual([
        { updates: { metadata_fetch_enabled: false } },
      ]);
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('the hint tooltip uses the disclaimer copy', async () => {
    const user = userEvent.setup();
    setupApi(ownerUser, { metadata_provider: 'thegamesdb', metadata_fetch_enabled: true });
    renderTab();

    const hint = await screen.findByRole('button', { name: 'About metadata fetching' });
    await user.hover(hint);

    expect((await screen.findAllByText(METADATA_FETCH_DISCLAIMER)).length).toBeGreaterThan(0);
  });

  it('is read-only for a non-owner settings manager', async () => {
    // The toggle is also disabled before auth resolves (activeUser is null),
    // so wait for both the settings and the non-owner user to load first.
    // Settings say "on", so a checked toggle proves the settings query landed.
    const user = userEvent.setup();
    const calls = setupApi(settingsManager, {
      metadata_provider: 'thegamesdb',
      metadata_fetch_enabled: true,
    });
    renderTab();

    const toggle = await findToggle();
    await waitFor(() => expect(toggle).toBeChecked());
    await waitFor(() =>
      expect(calls.some((c) => c.url === '/api/v1/auth/refresh' && c.method === 'POST')).toBe(true),
    );
    expect(screen.getByRole('button', { name: 'About metadata fetching' })).toBeInTheDocument();
    // Owner-only cards stay hidden for the resolved non-owner user.
    expect(
      screen.queryByText(/API key for TheGamesDB metadata enrichment/),
    ).not.toBeInTheDocument();

    expect(toggle).toBeDisabled();
    await user.click(toggle);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(patchCalls(calls)).toEqual([]);
  });
});
