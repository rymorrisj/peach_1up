import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StepEmulators from '@/pages/FirstRun/StepEmulators';
import type { EmulatorStatus } from '@/pages/FirstRun/types';

const EMULATORS: EmulatorStatus[] = [
  { slug: 'dosbox-x', name: 'DOSBox-X', required: true, available: true, path: '/bin/dosbox' },
  { slug: 'duckstation', name: 'DuckStation', required: true, available: false, path: null },
];

function renderStep(
  overrides: {
    emulators?: EmulatorStatus[];
    onNext?: () => void;
    onSkip?: () => void;
    onFinishAndGoTo?: (target: string) => void;
  } = {},
) {
  return render(
    <StepEmulators
      emulators={overrides.emulators ?? EMULATORS}
      onNext={overrides.onNext ?? vi.fn()}
      onSkip={overrides.onSkip ?? vi.fn()}
      onFinishAndGoTo={overrides.onFinishAndGoTo ?? vi.fn()}
    />,
  );
}

describe('StepEmulators', () => {
  it('shows the ready/required summary', () => {
    renderStep();
    expect(screen.getByText('1 of 2 required emulators ready.')).toBeInTheDocument();
  });

  it('falls back to a generic message when nothing is required', () => {
    renderStep({ emulators: [] });
    expect(screen.getByText('No emulators are marked required yet.')).toBeInTheDocument();
  });

  it('calls onFinishAndGoTo with /emulators when the finish-and-go button is clicked', async () => {
    const user = userEvent.setup();
    const onFinishAndGoTo = vi.fn();
    renderStep({ onFinishAndGoTo });
    await user.click(screen.getByRole('button', { name: 'Finish setup & go to Emulators →' }));
    expect(onFinishAndGoTo).toHaveBeenCalledWith('/emulators');
  });

  it('calls onNext when Next is clicked', async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    renderStep({ onNext });
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }));
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it('calls onSkip when Skip setup is clicked', async () => {
    const user = userEvent.setup();
    const onSkip = vi.fn();
    renderStep({ onSkip });
    await user.click(screen.getByRole('button', { name: 'Skip setup' }));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });
});
