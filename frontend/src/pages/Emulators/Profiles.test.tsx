import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import Profiles from '@/pages/Emulators/Profiles';
import { apiFetch } from '@/api/client';
import type { components } from '@shared/types';

type LaunchProfile = components['schemas']['ProfileItemRead'];
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

const PROFILE_ONE: LaunchProfile = {
  id: 1,
  name: 'DOS 486DX2 / SB16',
  slug: 'dos-486dx2-sb16',
  emulator_slug: 'dosbox-x',
  era: 'dos',
  extra_args: null,
  is_bundled: false,
  enable_networking: false,
  enable_dgvoodoo2: false,
  notes: null,
  launch_commands: null,
  use_drive: true,
  container_enabled: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const PROFILE_TWO: LaunchProfile = {
  id: 2,
  name: 'PS1 Default',
  slug: 'ps1-default',
  emulator_slug: 'duckstation',
  era: 'ps1',
  extra_args: null,
  is_bundled: true,
  enable_networking: false,
  enable_dgvoodoo2: false,
  notes: null,
  launch_commands: null,
  use_drive: true,
  container_enabled: null,
  created_at: '2024-01-02T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
};

const EMULATORS: CatalogEntry[] = [
  {
    slug: 'dosbox-x',
    name: 'DOSBox-X',
    version: '2024.07.01',
    description: 'DOS emulator.',
    license: 'GPL-2.0',
    install_type: 'zip',
    required: false,
    is_installed: true,
    install_path: 'C:\\emulators\\dosbox-x\\dosbox-x.exe',
    supported_formats: ['exe'],
    container_enabled: false,
    container_hardcap_disabled: false,
    skip_cpu_limit: false,
    skip_memory_limit: false,
    known_limitations: [],
  },
];

function mockApi() {
  vi.mocked(apiFetch).mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/api/v1/profile-items')) {
      return Promise.resolve({ items: [PROFILE_ONE, PROFILE_TWO], total: 2, limit: 50, offset: 0 });
    }
    if (typeof url === 'string' && url.includes('/api/v1/emulator-items')) {
      return Promise.resolve(EMULATORS);
    }
    return Promise.resolve([]);
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname}</div>;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/emulators/profiles']}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <Profiles />
            <LocationProbe />
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Profiles (Emulators sibling tab), CRUD via modal', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders the promoted cross-emulator, paginated list', async () => {
    mockApi();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('DOS 486DX2 / SB16')).toBeInTheDocument();
      expect(screen.getByText('PS1 Default')).toBeInTheDocument();
    });
  });

  it('opens the ProfileForm modal in create mode without navigating anywhere', async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('DOS 486DX2 / SB16')).toBeInTheDocument());

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '+ Add Profile' }));

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Add Launch Profile' })).toBeInTheDocument();
    });
    // Locked decision 11: editing is modal-only, there is no per-profile route.
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/emulators/profiles');
  });

  it('opens the ProfileForm modal in edit mode, pre-filled, without navigating to a :slug route', async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('DOS 486DX2 / SB16')).toBeInTheDocument());

    const editButtons = screen.getAllByRole('button', { name: 'Edit' });
    await user.click(editButtons[0]);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Edit Launch Profile' })).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('DOS 486DX2 / SB16')).toBeInTheDocument();
    expect(screen.getByDisplayValue('dos-486dx2-sb16')).toBeInTheDocument();
    // Still on the flat list route, clicking Edit opened a modal, not a navigation.
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/emulators/profiles');
  });

  it('does not render a Delete action for a bundled/default profile', async () => {
    mockApi();
    renderPage();
    await waitFor(() => expect(screen.getByText('PS1 Default')).toBeInTheDocument());
    // PROFILE_ONE (not bundled) gets a Delete button, PROFILE_TWO (is_bundled) does not.
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(1);
  });

  it('regression guard: source never navigates to a per-profile URL (the retired P2 bug pattern)', () => {
    // dev_docs/v2/08_emulator_profiles_navigation.md, P2: the old read-only
    // Profiles view row-clicked into an unregistered `/profiles/${slug}`
    // route. This doc's locked decision 11 explicitly removes any per-profile
    // route, guard against either form (the old `/profiles/` or a
    // hypothetical `/emulators/profiles/`) creeping back into the promoted
    // component via a `navigate(...)` call.
    const profilesSource = fs.readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), 'Profiles.tsx'),
      'utf-8',
    );
    expect(profilesSource).not.toMatch(/navigate\(/);
    // Scoped to an actual navigate() call target, not any string containing
    // `/profiles/${`, this guards the retired UI route pattern specifically
    // (the REST calls in handleSubmit/handleDelete now hit
    // `/api/v1/profile-items/${...}` and no longer risk matching this bare
    // substring at all).
    expect(profilesSource).not.toMatch(/navigate\(\s*[`'"]\/(?:emulators\/)?profiles\/\$\{/);
  });
});
