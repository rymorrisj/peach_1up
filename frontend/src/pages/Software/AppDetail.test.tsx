import { screen, waitFor, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import AppDetail from '@/pages/Software/AppDetail';
import { apiFetch } from '@/api/client';

// Basic smoke coverage only, not exhaustive behavior coverage (that's the
// existing CollectionDetail*.test.tsx depth, planned separately for a full
// audit before beta). This just catches a render-breaks-completely
// regression, same apiFetch-mocking approach as CollectionDetail's tests.
// The edit-form cases below are similarly basic: render, field edit, save
// PATCH body, not the field-by-field depth of CollectionDetail.editform.test.tsx.
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

const plainUser = {
  id: 1,
  name: 'Player',
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
};

function minimalApp(overrides?: Record<string, unknown>) {
  return {
    id: 1,
    slug: 'my-app',
    title: 'My App',
    description: null,
    tags: [],
    linked_items: [],
    era: 'winxp',
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
        app_item_bundle_id: 1,
        file_path: '/apps/myapp.exe',
        executable_path: null,
        cover_art_path: null,
        cover_art_url: null,
      },
    ],
    ...overrides,
  };
}

const oneEnvironment = [
  {
    id: 5,
    name: 'My XP Box',
    era: 'winxp',
    emulator_slug: '86box',
    is_system: false,
    is_present: true,
    installed_at: '2026-01-01T00:00:00Z',
  },
];

interface RecordedCall {
  url: string;
  method?: string;
  body?: unknown;
}

function mockApi(app: unknown, environments: unknown[] = []) {
  const calls: RecordedCall[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: unknown) => {
    if (typeof url !== 'string') return Promise.resolve([]);
    const method = (init as { method?: string } | undefined)?.method;
    const bodyRaw = (init as { body?: string } | undefined)?.body;
    calls.push({ url, method, body: bodyRaw ? JSON.parse(bodyRaw) : undefined });
    if (url === '/api/v1/auth/me') return Promise.resolve(plainUser);
    if (url === '/api/v1/auth/refresh') return Promise.resolve({ user: plainUser });
    if (url === '/api/v1/app-item-bundle/1' && (!method || method === 'GET'))
      return Promise.resolve(app);
    if (url === '/api/v1/app-item-bundle/1' && method === 'PATCH') return Promise.resolve({});
    if (url === '/api/v1/app-item/100' && method === 'PATCH') return Promise.resolve({});
    if (url === '/api/v1/environment-items') return Promise.resolve(environments);
    return Promise.resolve([]);
  });
  return calls;
}

// Radix Select's trigger is not a native <select>, userEvent.selectOptions
// does not work against it. Open the listbox by clicking the labeled
// trigger, then click the option by its visible text (the option's label,
// not its underlying value, Radix's listbox is queried by accessible name).
async function selectRadixOption(
  user: ReturnType<typeof userEvent.setup>,
  triggerName: string,
  optionName: string,
) {
  await user.click(screen.getByRole('combobox', { name: triggerName }));
  await user.click(await screen.findByRole('option', { name: optionName }));
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/software/apps/1']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/software/apps/:id" element={<AppDetail />} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('AppDetail', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders without throwing given a minimal app fixture', async () => {
    mockApi(minimalApp());
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('My App')[0]).toBeInTheDocument();
    });
  });

  describe('edit form', () => {
    it('renders the edit form pre-filled from the entity, showing Platform for a PC era', async () => {
      mockApi(minimalApp({ title: 'My App', era: 'winxp' }), oneEnvironment);
      renderPage();

      await waitFor(() => {
        expect(screen.getByLabelText('Title')).toHaveValue('My App');
      });
      expect(screen.getByRole('combobox', { name: 'Era' })).toHaveTextContent('Windows XP');
      expect(screen.getByLabelText('Platform')).toBeInTheDocument();
    });

    it('shows the Platform field disabled with an explanatory note for a console era', async () => {
      mockApi(minimalApp({ era: 'ps1', is_pc: false }));
      renderPage();

      await screen.findByLabelText('Title');
      const platformSelect = screen.getByLabelText('Platform');
      expect(platformSelect).toBeInTheDocument();
      expect(platformSelect).toBeDisabled();
      expect(
        screen.getByText('Determined automatically by platform type, no environment needed.'),
      ).toBeInTheDocument();
    });

    it('clears environment_item_id and disables the field when era changes to console', async () => {
      const user = userEvent.setup();
      mockApi(minimalApp({ era: 'winxp', is_pc: true, environment_item_id: 5 }), oneEnvironment);
      renderPage();

      await screen.findByLabelText('Title');
      expect(screen.getByRole('combobox', { name: 'Platform' })).toHaveTextContent('My XP Box');
      expect(screen.getByRole('combobox', { name: 'Platform' })).not.toBeDisabled();

      await selectRadixOption(user, 'Era', 'PlayStation 1');
      const platformSelect = screen.getByRole('combobox', { name: 'Platform' });
      expect(platformSelect).toBeDisabled();
      expect(platformSelect).toHaveTextContent('No platform selected');
    });

    it('sends the expected PATCH bodies on save', async () => {
      const user = userEvent.setup();
      const calls = mockApi(minimalApp({ era: 'winxp', is_pc: true }), oneEnvironment);
      renderPage();

      const title = await screen.findByLabelText('Title');
      await user.clear(title);
      await user.type(title, 'Renamed App');
      await selectRadixOption(user, 'Platform', 'My XP Box');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => {
        const bundlePatch = calls.find(
          (c) => c.url === '/api/v1/app-item-bundle/1' && c.method === 'PATCH',
        );
        expect(bundlePatch).toBeTruthy();
        expect(bundlePatch?.body).toMatchObject({
          title: 'Renamed App',
          era: 'winxp',
          environment_item_id: 5,
        });
        expect(bundlePatch?.body).not.toHaveProperty('is_pc');

        const leafPatch = calls.find(
          (c) => c.url === '/api/v1/app-item/100' && c.method === 'PATCH',
        );
        expect(leafPatch).toBeTruthy();
        expect(leafPatch?.body).toMatchObject({ cover_art_path: null });
      });
    });
  });
});
