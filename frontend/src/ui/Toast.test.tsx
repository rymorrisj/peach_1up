import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as RadixToast from '@radix-ui/react-toast';
import { Toast } from '@/ui/Toast';

// Toast.Root requires a Toast.Provider ancestor, it throws otherwise (real
// consumers always get this for free via ui/ToastProvider.tsx). A Viewport
// is included too so each Root has a real portal target, matching how it is
// actually used, not just enough to avoid the throw.
function renderToast(ui: React.ReactElement) {
  return render(
    <RadixToast.Provider>
      {ui}
      <RadixToast.Viewport />
    </RadixToast.Provider>,
  );
}

describe('Toast', () => {
  it('renders the message', () => {
    renderToast(<Toast message="Saved successfully" onDismiss={vi.fn()} />);
    expect(screen.getByText('Saved successfully')).toBeInTheDocument();
  });

  it('calls onDismiss when the dismiss button is clicked', async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    renderToast(<Toast message="Something failed" onDismiss={onDismiss} />);
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('calls onDismiss when the toast body is clicked', async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    renderToast(<Toast message="Click to dismiss" onDismiss={onDismiss} />);
    await user.click(screen.getByRole('alert'));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  // Radix's own close timer (node_modules/@radix-ui/react-toast ToastImpl)
  // starts unconditionally on mount whenever isClosePausedRef is false, its
  // default state, it does not read document.hasFocus() anywhere. Pause and
  // resume only happen in response to real focusin/pointermove/blur/focus
  // events fired after mount. Real timers are used here, not
  // vi.useFakeTimers, because verifying this against jsdom's fake clock
  // requires the exact tick at which React flushes ToastImpl's mount effect
  // relative to the fake clock advancing, which cannot be confirmed by
  // reading source alone.
  it('auto-dismisses after the given duration', async () => {
    const onDismiss = vi.fn();
    renderToast(<Toast message="Auto dismiss" duration={50} onDismiss={onDismiss} />);
    expect(onDismiss).not.toHaveBeenCalled();
    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1));
  });

  it('does not auto-dismiss when duration is 0', async () => {
    const onDismiss = vi.fn();
    renderToast(<Toast message="Sticky" duration={0} onDismiss={onDismiss} />);
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('renders each variant without crashing', () => {
    const variants = ['success', 'error', 'info'] as const;
    for (const variant of variants) {
      const { unmount } = renderToast(
        <Toast message="Label" variant={variant} onDismiss={vi.fn()} />,
      );
      expect(screen.getByRole('alert')).toBeInTheDocument();
      unmount();
    }
  });
});
