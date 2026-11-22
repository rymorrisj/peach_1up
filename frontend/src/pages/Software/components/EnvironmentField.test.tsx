import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { apiFetch } from '@/api/client';
import { renderWithProviders } from '@/test/helpers';
import { EnvironmentField } from './EnvironmentField';

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
}));

const mockApiFetch = vi.mocked(apiFetch);

// Rows as GET /api/v1/environment-items?platform=<value> returns them; the
// server computes launch_blocked_reason, the field only presents it.
function makeEnvironment(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    name: 'Win98 Box',
    platform: 'win98',
    emulator_slug: '86box',
    slug: 'win98-box',
    is_system: false,
    installed_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    is_present: true,
    launch_blocked_reason: null,
    ...overrides,
  };
}

function renderField(platform: string, rows: unknown[] = [makeEnvironment()]) {
  mockApiFetch.mockResolvedValue(rows as never);
  return renderWithProviders(
    <MemoryRouter>
      <EnvironmentField platform={platform} value="" onChange={vi.fn()} />
    </MemoryRouter>,
  );
}

async function openDropdown(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('combobox', { name: 'Environment' }));
}

beforeEach(() => {
  mockApiFetch.mockReset();
});

describe('EnvironmentField', () => {
  it('is shown for a PC platform and queries with that platform', async () => {
    renderField('win98');

    expect(await screen.findByRole('combobox', { name: 'Environment' })).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/environment-items?platform=win98');
  });

  it.each(['ps1', 'n64', 'xbox360', 'unknown'])(
    'is hidden and never fetches for the non-PC platform %s',
    (platform) => {
      renderField(platform);

      expect(screen.queryByRole('combobox', { name: 'Environment' })).not.toBeInTheDocument();
      expect(mockApiFetch).not.toHaveBeenCalled();
    },
  );

  it('lists an Environment of another platform as selectable, with no compatibility filter', async () => {
    const user = userEvent.setup();
    renderField('winxp', [makeEnvironment({ platform: 'win95', name: 'Win95 Box' })]);
    await openDropdown(user);

    const option = await screen.findByRole('option', { name: 'Win95 Box' });
    expect(option).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('leaves out system catalog rows, matching the Environments page', async () => {
    const user = userEvent.setup();
    renderField('win98', [
      makeEnvironment(),
      makeEnvironment({ id: 2, name: '86Box', slug: '86box', is_system: true }),
    ]);
    await openDropdown(user);

    expect(await screen.findByRole('option', { name: 'Win98 Box' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /86Box/ })).not.toBeInTheDocument();
  });

  it.each([
    ['environment_not_present', 'image files missing, fix its paths on the Environments page'],
    ['environment_not_provisioned', 'no disk image yet, set one up on the Environments page'],
    [
      'environment_not_installed',
      'OS not installed yet, launch it from the Environments page and mark it installed',
    ],
  ])('disables a candidate blocked by %s with a next-step reason', async (reason, label) => {
    const user = userEvent.setup();
    renderField('win98', [makeEnvironment({ launch_blocked_reason: reason })]);
    await openDropdown(user);

    const option = await screen.findByRole('option', { name: `Win98 Box, ${label}` });
    expect(option).toHaveAttribute('aria-disabled', 'true');
  });

  it('disables, rather than hides, an unrecognized reason code', async () => {
    const user = userEvent.setup();
    renderField('win98', [makeEnvironment({ launch_blocked_reason: 'some_future_reason' })]);
    await openDropdown(user);

    const option = await screen.findByRole('option', { name: 'Win98 Box, some_future_reason' });
    expect(option).toHaveAttribute('aria-disabled', 'true');
  });

  it('links to the Environments page when no Environments exist', async () => {
    renderField('dos', []);

    const link = await screen.findByRole('link', { name: 'Create one on the Environments page' });
    expect(link).toHaveAttribute('href', '/environments');
  });

  it('shows no create link while Environments exist', async () => {
    renderField('dos', [makeEnvironment({ platform: 'dos', name: 'DOS' })]);

    await screen.findByRole('combobox', { name: 'Environment' });
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalled());
    expect(
      screen.queryByRole('link', { name: 'Create one on the Environments page' }),
    ).not.toBeInTheDocument();
  });
});
