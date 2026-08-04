import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiFetch } from '@/api/client';
import FirstRun from '@/pages/FirstRun';

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

// Owner already exists so the wizard starts on the Software step directly,
// this suite doesn't touch the StepWelcome/Step0Owner/PIN flow.
function mockFirstRunApi() {
  vi.mocked(apiFetch).mockImplementation((path: string) => {
    if (path === '/api/v1/settings/first-run-status') {
      return Promise.resolve({
        first_run_complete: false,
        owner_exists: true,
        emulators: [],
        paths: {},
      }) as ReturnType<typeof apiFetch>;
    }
    if (path === '/api/v1/settings/complete-first-run') {
      return Promise.resolve(undefined) as ReturnType<typeof apiFetch>;
    }
    if (path.startsWith('/api/v1/bios')) {
      return Promise.resolve({ items: [], total: 0, limit: 200, offset: 0 }) as ReturnType<
        typeof apiFetch
      >;
    }
    return Promise.resolve(undefined) as ReturnType<typeof apiFetch>;
  });
}

function renderWizard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/first-run']}>
        <FirstRun />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Navigates from the Software step (the wizard's start point when the owner
// already exists) through Users to land on Emulators, the shared entry point
// most tests below need.
async function goToEmulators(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => screen.getByRole('button', { name: 'Next: Users' }));
  await user.click(screen.getByRole('button', { name: 'Next: Users' }));
  await waitFor(() => screen.getByRole('button', { name: 'Next: Emulators' }));
  await user.click(screen.getByRole('button', { name: 'Next: Emulators' }));
  await waitFor(() => screen.getByRole('heading', { name: 'Emulators' }));
}

describe('FirstRun wizard', () => {
  // jsdom's window.location.replace is non-configurable, so it can't be
  // spied on directly with vi.spyOn, replace the whole location object instead.
  let replaceSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    replaceSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { ...window.location, replace: replaceSpy },
      writable: true,
      configurable: true,
    });
    mockFirstRunApi();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('starts on the Software step when the owner already exists', async () => {
    renderWizard();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Your library, organized' })).toBeInTheDocument();
    });
  });

  it('advances from Emulators to BIOS on Next', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }));
    expect(screen.getByRole('heading', { name: 'BIOS Files' })).toBeInTheDocument();
  });

  it('returns from BIOS to Emulators on Back', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }));
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('heading', { name: 'Emulators' })).toBeInTheDocument();
  });

  // Skip used to complete first-run immediately. With Important Settings and
  // Guides now living after BIOS, Skip advances to Important Settings instead
  // so those two steps stay reachable, actual completion now only happens
  // from the Guides step.
  it('advances to Important Settings instead of finishing when Skip is clicked on the Emulators step', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await user.click(screen.getByRole('button', { name: 'Skip setup' }));
    expect(
      screen.getByRole('heading', { name: 'A few things worth knowing before you start' }),
    ).toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalledWith('/api/v1/settings/complete-first-run', {
      method: 'POST',
    });
  });

  // Same change as above, for BIOS's Finish button.
  it('advances to Important Settings instead of finishing when Finish is clicked on the BIOS step', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }));
    await waitFor(() => screen.getByRole('button', { name: 'Finish' }));
    await user.click(screen.getByRole('button', { name: 'Finish' }));
    expect(
      screen.getByRole('heading', { name: 'A few things worth knowing before you start' }),
    ).toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalledWith('/api/v1/settings/complete-first-run', {
      method: 'POST',
    });
  });

  it('calls complete-first-run and redirects to / when Finish is clicked on the Guides step', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }));
    await waitFor(() => screen.getByRole('button', { name: 'Finish' }));
    await user.click(screen.getByRole('button', { name: 'Finish' })); // BIOS -> Important Settings
    await waitFor(() => screen.getByRole('button', { name: 'Next: Guides' }));
    await user.click(screen.getByRole('button', { name: 'Next: Guides' })); // -> Guides
    await waitFor(() => screen.getByRole('button', { name: 'Finish' }));
    await user.click(screen.getByRole('button', { name: 'Finish' })); // Guides -> complete
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', {
        method: 'POST',
      });
    });
    expect(replaceSpy).toHaveBeenCalledWith('/');
  });

  it('calls complete-first-run and redirects to /emulators when the Emulators step finish-and-go button is clicked', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await waitFor(() => screen.getByRole('button', { name: 'Finish setup & go to Emulators →' }));
    await user.click(screen.getByRole('button', { name: 'Finish setup & go to Emulators →' }));
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', {
        method: 'POST',
      });
    });
    expect(replaceSpy).toHaveBeenCalledWith('/emulators');
  });

  it('calls complete-first-run and redirects to /emulators/bios when the BIOS step finish-and-go button is clicked', async () => {
    const user = userEvent.setup();
    renderWizard();
    await goToEmulators(user);
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }));
    await waitFor(() => screen.getByRole('button', { name: 'Finish setup & go to BIOS →' }));
    await user.click(screen.getByRole('button', { name: 'Finish setup & go to BIOS →' }));
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', {
        method: 'POST',
      });
    });
    expect(replaceSpy).toHaveBeenCalledWith('/emulators/bios');
  });
});
