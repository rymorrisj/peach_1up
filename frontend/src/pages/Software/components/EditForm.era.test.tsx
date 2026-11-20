import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EditForm, type EraConfirmAction } from './EditForm';
import type { EraReview } from './eraReview';
import type { SoftwareGameForm } from '../types/gameForm';

// EditForm renders the launch-file-extensions query, the one thing it fetches.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(() => Promise.resolve({ extensions: [] })),
  ApiError: class ApiError extends Error {},
}));

const ADVICE =
  "If the game won't launch, look up the correct platform (e.g. PS1, Xbox) and set the era manually.";

const form: SoftwareGameForm = {
  title: 'Ico',
  sort_title: '',
  description: '',
  publisher: '',
  year: '',
  category: '',
  cover_art_path: '',
  content_rating: '',
  era: 'ps2',
  environment_item_id: '',
  profile_item_id: '',
  executable_path: '',
};

interface RenderOptions {
  eraReview?: EraReview;
  era?: string;
  reason?: string | null;
  eraConfirm?: EraConfirmAction;
}

function renderForm({ eraReview, era = 'ps2', reason = null, eraConfirm }: RenderOptions) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <EditForm
        item={{ era, era_review: eraReview, detection_reason: reason }}
        form={{ ...form, era: era === 'unknown' ? '' : era }}
        setField={() => {}}
        handleSave={() => {}}
        saving={false}
        saveError={null}
        saveSuccess={false}
        execBrowserOpen={false}
        setExecBrowserOpen={() => {}}
        profiles={[]}
        platforms={[]}
        eraConfirm={eraConfirm}
      />
    </QueryClientProvider>,
  );
}

describe('EditForm era field treatment', () => {
  describe('warning ring', () => {
    it('is drawn when era_review is unreviewed', () => {
      renderForm({ eraReview: 'unreviewed' });
      expect(screen.getByTestId('era-select-wrapper').className).toContain('ring-warning');
    });

    it.each(['verified', 'confirmed'] as const)('is not drawn when era_review is %s', (review) => {
      renderForm({ eraReview: review });
      expect(screen.getByTestId('era-select-wrapper').className).not.toContain('ring-');
    });

    it('is not drawn when era_review is absent', () => {
      renderForm({});
      expect(screen.getByTestId('era-select-wrapper').className).not.toContain('ring-');
    });

    it('never uses green', () => {
      renderForm({ eraReview: 'verified' });
      expect(screen.getByTestId('era-select-wrapper').className).not.toContain('success');
    });

    it('does not render the old status badge', () => {
      renderForm({ eraReview: 'unreviewed' });
      expect(screen.queryByText('Era unreviewed')).not.toBeInTheDocument();
      expect(screen.queryByText('Era verified')).not.toBeInTheDocument();
      expect(screen.queryByText('Era set by you')).not.toBeInTheDocument();
    });
  });

  describe('hint tooltip', () => {
    async function hoverHint(user: ReturnType<typeof userEvent.setup>) {
      await user.hover(screen.getByRole('button', { name: 'About this platform' }));
      return screen.findByRole('tooltip');
    }

    it('explains an unreviewed era and where it was detected from', async () => {
      renderForm({ eraReview: 'unreviewed', reason: 'CHD header' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(
        `Highlighted because this platform was detected, not verified. Detected from: CHD header. ${ADVICE}`,
      );
    });

    it('says nothing was detected for an unknown era', async () => {
      renderForm({ eraReview: 'unreviewed', era: 'unknown' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(`No platform was detected. ${ADVICE}`);
    });

    it('explains a verified era', async () => {
      renderForm({ eraReview: 'verified', reason: 'CHD header' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(`Verified against the hash index. ${ADVICE}`);
    });

    it('explains a confirmed era', async () => {
      renderForm({ eraReview: 'confirmed', reason: 'CHD header' });
      const tooltip = await hoverHint(userEvent.setup());
      expect(tooltip).toHaveTextContent(
        `This platform is confirmed. Detected from: CHD header. ${ADVICE}`,
      );
    });

    it('opens on keyboard focus', async () => {
      renderForm({ eraReview: 'verified' });
      const hint = screen.getByRole('button', { name: 'About this platform' });
      act(() => hint.focus());
      await waitFor(() => {
        expect(screen.getByRole('tooltip')).toHaveTextContent('Verified against the hash index.');
      });
    });

    it('renders a disc-supplied reason as plain text, never as HTML', async () => {
      const reason = '<img src=x alt="injected"> <b>LABEL</b>';
      const { container } = renderForm({ eraReview: 'unreviewed', reason });
      await hoverHint(userEvent.setup());
      expect(screen.getAllByRole('tooltip')[0]).toHaveTextContent(reason);
      expect(document.body.querySelector('img[alt="injected"]')).toBeNull();
      expect(container.querySelector('b')).toBeNull();
      expect(document.body.querySelector('[role="tooltip"] b')).toBeNull();
    });

    it('caps the width and wraps long text', async () => {
      renderForm({ eraReview: 'unreviewed', reason: 'A'.repeat(200) });
      await hoverHint(userEvent.setup());
      const textBox = screen.getAllByText(/Detected from: A+/)[0];
      expect(textBox.className).toContain('max-w-xs');
      expect(textBox.className).toContain('break-words');
    });

    it('has no hint icon when era_review is absent', () => {
      renderForm({});
      expect(screen.queryByRole('button', { name: 'About this platform' })).not.toBeInTheDocument();
    });
  });

  describe('Confirm platform button', () => {
    it('is not rendered without an eraConfirm action', () => {
      renderForm({ eraReview: 'unreviewed' });
      expect(screen.queryByRole('button', { name: 'Confirm platform' })).not.toBeInTheDocument();
    });

    it('is rendered with its guidance line and calls onConfirm on click', async () => {
      const onConfirm = vi.fn();
      renderForm({
        eraReview: 'unreviewed',
        eraConfirm: { onConfirm, pending: false, error: null },
      });
      expect(
        screen.getByText("Only after you've seen the game run correctly."),
      ).toBeInTheDocument();
      await userEvent.setup().click(screen.getByRole('button', { name: 'Confirm platform' }));
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it('is disabled while the confirm request is pending', () => {
      renderForm({
        eraReview: 'unreviewed',
        eraConfirm: { onConfirm: vi.fn(), pending: true, error: null },
      });
      expect(screen.getByRole('button', { name: 'Confirm platform' })).toBeDisabled();
    });

    it('shows a failure loudly as an alert', () => {
      renderForm({
        eraReview: 'unreviewed',
        eraConfirm: { onConfirm: vi.fn(), pending: false, error: 'Permission denied.' },
      });
      expect(screen.getByRole('alert')).toHaveTextContent('Permission denied.');
      expect(screen.getByRole('button', { name: 'Confirm platform' })).toBeEnabled();
    });
  });
});
