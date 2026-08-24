import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PlatformField } from './PlatformField';

// PlatformField takes an already-fetched platforms array as a prop and does
// no fetching of its own, so this renders it directly with a fabricated
// server response instead of going through CollectionDetail/AppDetail's full
// react-query + apiFetch mocking setup. launch_blocked_reason values below
// simulate what GET /api/v1/environment-items?era=<value> now computes
// server-side (backend/api/routes/environments.py), the vocabulary this
// component consumes rather than reimplements.
function makePlatform(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    name: 'Win98 Box',
    era: 'win98',
    emulator_slug: '86box',
    slug: 'win98-box',
    is_system: false,
    installed_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    is_present: true,
    launch_blocked_reason: null,
    ...overrides,
  } as never;
}

// Radix Select's trigger is not a native <select>; open the listbox by
// clicking the labeled trigger, same pattern as
// CollectionDetail.editform.test.tsx's selectRadixOption.
async function openPlatformDropdown(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('combobox', { name: 'Platform' }));
}

describe('PlatformField', () => {
  it('renders a selectable option (no reason) as enabled with just its name', async () => {
    const user = userEvent.setup();
    render(
      <PlatformField
        isPcLaunchable
        value=""
        onChange={vi.fn()}
        platforms={[makePlatform({ launch_blocked_reason: null })]}
        disabledNote=""
      />,
    );
    await openPlatformDropdown(user);

    const option = await screen.findByRole('option', { name: 'Win98 Box' });
    expect(option).toBeInTheDocument();
    expect(option).not.toHaveAttribute('aria-disabled', 'true');
  });

  it.each([
    ['environment_era_mismatch', 'different era'],
    ['environment_not_present', 'not present'],
    ['environment_not_provisioned', 'not yet provisioned'],
    ['environment_not_installed', 'OS not installed yet'],
  ])('labels and disables a candidate whose server reason is %s', async (reason, label) => {
    const user = userEvent.setup();
    render(
      <PlatformField
        isPcLaunchable
        value=""
        onChange={vi.fn()}
        platforms={[makePlatform({ launch_blocked_reason: reason })]}
        disabledNote=""
      />,
    );
    await openPlatformDropdown(user);

    const option = await screen.findByRole('option', { name: `Win98 Box, ${label}` });
    expect(option).toBeInTheDocument();
    expect(option).toHaveAttribute('aria-disabled', 'true');
  });

  it('falls back to disabling on an unrecognized reason code, does not hide it', async () => {
    const user = userEvent.setup();
    render(
      <PlatformField
        isPcLaunchable
        value=""
        onChange={vi.fn()}
        platforms={[makePlatform({ launch_blocked_reason: 'some_future_reason' })]}
        disabledNote=""
      />,
    );
    await openPlatformDropdown(user);

    const option = await screen.findByRole('option', { name: 'Win98 Box, some_future_reason' });
    expect(option).toBeInTheDocument();
    expect(option).toHaveAttribute('aria-disabled', 'true');
  });

  it('shows no platform options at all when isPcLaunchable is false', () => {
    render(
      <PlatformField
        isPcLaunchable={false}
        value=""
        onChange={vi.fn()}
        platforms={[makePlatform({ launch_blocked_reason: null })]}
        disabledNote="Determined automatically by era, no environment needed."
      />,
    );

    expect(screen.getByRole('combobox', { name: 'Platform' })).toBeDisabled();
    expect(
      screen.getByText('Determined automatically by era, no environment needed.'),
    ).toBeInTheDocument();
  });
});
