import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { EditForm, type PlatformConfirmAction } from './EditForm';
import type { PlatformReview } from './platformReview';
import type { SoftwareGameForm } from '../types/gameForm';

// EditForm fetches launch-file-extensions; its EnvironmentField fetches the
// Environment list for a PC platform.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn((url: string) =>
    Promise.resolve(url.startsWith('/api/v1/environment-items') ? [] : { extensions: [] }),
  ),
  ApiError: class ApiError extends Error {},
}));

const ADVICE =
  "If the game won't launch, look up the correct platform (e.g. PS1, Xbox) and set it manually.";

const form: SoftwareGameForm = {
  title: 'Ico',
  sort_title: '',
  description: '',
  publisher: '',
  year: '',
  category: '',
  cover_art_path: '',
  content_rating: '',
  platform: 'ps2',
  environment_item_id: '',
  profile_item_id: '',
  executable_path: '',
};

interface RenderOptions {
  platformReview?: PlatformReview;
  platform?: string;
  reason?: string | null;
  platformConfirm?: PlatformConfirmAction;
  setField?: (key: string, value: unknown) => void;
}

function renderForm({
  platformReview,
  platform = 'ps2',
  reason = null,
  platformConfirm,
  setField = () => {},
}: RenderOptions) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EditForm
          item={{ platform, platform_review: platformReview, detection_reason: reason }}
          form={{ ...form, platform: platform === 'unknown' ? '' : platform }}
          setField={setField}
          handleSave={() => {}}
          saving={false}
          saveError={null}
          saveSuccess={false}
          execBrowserOpen={false}
          setExecBrowserOpen={() => {}}
          profiles={[]}
          platformConfirm={platformConfirm}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('EditForm platform field treatment', () => {
  describe('warning ring', () => {
    it('is drawn when platform_review is unreviewed', () => {
      renderForm({ platformReview: 'unreviewed' });
      expect(screen.getByTestId('platform-select-wrapper').className).toContain('ring-warning');
    });

    it.each(['verified', 'confirmed'] as const)(
      'is not drawn when platform_review is %s',
      (review) => {
        renderForm({ platformReview: review });
        expect(screen.getByTestId('platform-select-wrapper').className).not.toContain('ring-');
      },
    );

    it('is not drawn when platform_review is absent', () => {
      renderForm({});
      expect(screen.getByTestId('platform-select-wrapper').className).not.toContain('ring-');
    });

    it('never uses green', () => {
      renderForm({ platformReview: 'verified' });
      expect(screen.getByTestId('platform-select-wrapper').className).not.toContain('success');
    });

    it('does not render the old status badge', () => {
      renderForm({ platformReview: 'unreviewed' });
      expect(screen.queryByText('Platform unreviewed')).not.toBeInTheDocument();
      expect(screen.queryByText('Platform verified')).not.toBeInTheDocument();
      expect(screen.queryByText('Platform set by you')).not.toBeInTheDocument();
    });
  });

  describe('hint tooltip', () => {
    async function hoverHint(user: ReturnType<typeof userEvent.setup>) {
      await user.hover(screen.getByRole('button', { name: 'About this platform' }));
      return screen.findByRole('tooltip');
    }

    it('explains an unreviewed platform and where it was detected from', async () => {
      renderForm({ platformReview: 'unreviewed', reason: 'CHD header' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(
        `Highlighted because this platform was detected, not verified. Detected from: CHD header. ${ADVICE}`,
      );
    });

    it('says nothing was detected for an unknown platform', async () => {
      renderForm({ platformReview: 'unreviewed', platform: 'unknown' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(`No platform was detected. ${ADVICE}`);
    });

    it('explains a verified platform', async () => {
      renderForm({ platformReview: 'verified', reason: 'CHD header' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(`Verified against the hash index. ${ADVICE}`);
    });

    it('explains a confirmed platform', async () => {
      renderForm({ platformReview: 'confirmed', reason: 'CHD header' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(
        `This platform is confirmed. Detected from: CHD header. ${ADVICE}`,
      );
    });

    it('opens on keyboard focus', async () => {
      renderForm({ platformReview: 'verified' });
      const hint = screen.getByRole('button', { name: 'About this platform' });
      act(() => hint.focus());
      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toHaveTextContent('Verified against the hash index.');
      });
    });

    it('renders a disc-supplied reason as plain text, never as HTML', async () => {
      const reason = '<img src=x alt="injected"> <b>LABEL</b>';
      const { container } = renderForm({ platformReview: 'unreviewed', reason });
      await hoverHint(userEvent.setup());
      expect(screen.getAllByRole('tooltip')[0]).toHaveTextContent(reason);
      expect(document.body.querySelector('img[alt="injected"]')).toBeNull();
      expect(container.querySelector('b')).toBeNull();
      expect(document.body.querySelector('[role="tooltip"] b')).toBeNull();
    });

    it('caps the width and wraps long text', async () => {
      renderForm({ platformReview: 'unreviewed', reason: 'A'.repeat(200) });
      await hoverHint(userEvent.setup());
      const textBox = screen.getAllByText(/Detected from: A+/)[0];
      expect(textBox.className).toContain('max-w-xs');
      expect(textBox.className).toContain('break-words');
    });

    it('has no hint icon when platform_review is absent', () => {
      renderForm({});
      expect(screen.queryByRole('button', { name: 'About this platform' })).not.toBeInTheDocument();
    });
  });

  describe('Confirm platform button', () => {
    it('is not rendered without an platformConfirm action', () => {
      renderForm({ platformReview: 'unreviewed' });
      expect(screen.queryByRole('button', { name: 'Confirm platform' })).not.toBeInTheDocument();
    });

    it('is rendered with its guidance line and calls onConfirm on click', async () => {
      const onConfirm = vi.fn();
      renderForm({
        platformReview: 'unreviewed',
        platformConfirm: { onConfirm, pending: false, error: null },
      });
      expect(
        screen.getByText("Only after you've seen the game run correctly."),
      ).toBeInTheDocument();
      await userEvent.setup().click(screen.getByRole('button', { name: 'Confirm platform' }));
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it('is disabled while the confirm request is pending', () => {
      renderForm({
        platformReview: 'unreviewed',
        platformConfirm: { onConfirm: vi.fn(), pending: true, error: null },
      });
      expect(screen.getByRole('button', { name: 'Confirm platform' })).toBeDisabled();
    });

    it('shows a failure loudly as an alert', () => {
      renderForm({
        platformReview: 'unreviewed',
        platformConfirm: { onConfirm: vi.fn(), pending: false, error: 'Permission denied.' },
      });
      expect(screen.getByRole('alert')).toHaveTextContent('Permission denied.');
      expect(screen.getByRole('button', { name: 'Confirm platform' })).toBeEnabled();
    });
  });

  describe('Platform select and Environment sub-field', () => {
    it('groups every platform under PC and Console', async () => {
      const user = userEvent.setup();
      renderForm({ platform: 'ps2' });
      await user.click(screen.getByRole('combobox', { name: 'Platform' }));

      const pc = await screen.findByRole('group', { name: 'PC' });
      const consoleGroup = screen.getByRole('group', { name: 'Console' });
      expect(within(pc).getByRole('option', { name: 'Windows 98' })).toBeInTheDocument();
      expect(within(pc).queryByRole('option', { name: 'PlayStation 2' })).not.toBeInTheDocument();
      expect(
        within(consoleGroup).getByRole('option', { name: 'PlayStation 2' }),
      ).toBeInTheDocument();
      expect(within(consoleGroup).getByRole('option', { name: 'Xbox 360' })).toBeInTheDocument();
    });

    it('shows the Environment field only for a PC platform', async () => {
      renderForm({ platform: 'win98' });
      expect(await screen.findByRole('combobox', { name: 'Environment' })).toBeInTheDocument();
    });

    it('hides the Environment field for a console platform', () => {
      renderForm({ platform: 'ps2' });
      expect(screen.queryByRole('combobox', { name: 'Environment' })).not.toBeInTheDocument();
    });

    it('clears the Environment when a console platform is chosen', async () => {
      const user = userEvent.setup();
      const setField = vi.fn();
      renderForm({ platform: 'win98', setField });
      await user.click(screen.getByRole('combobox', { name: 'Platform' }));
      await user.click(await screen.findByRole('option', { name: 'PlayStation 1' }));

      expect(setField).toHaveBeenCalledWith('platform', 'ps1');
      expect(setField).toHaveBeenCalledWith('environment_item_id', '');
    });

    it('keeps the Environment when another PC platform is chosen', async () => {
      const user = userEvent.setup();
      const setField = vi.fn();
      renderForm({ platform: 'win98', setField });
      await user.click(screen.getByRole('combobox', { name: 'Platform' }));
      await user.click(await screen.findByRole('option', { name: 'Windows XP' }));

      expect(setField).toHaveBeenCalledWith('platform', 'winxp');
      expect(setField).not.toHaveBeenCalledWith('environment_item_id', '');
    });
  });
});
