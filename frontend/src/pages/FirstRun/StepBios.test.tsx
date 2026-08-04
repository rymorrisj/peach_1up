import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiFetch } from '@/api/client';
import StepBios from '@/pages/FirstRun/StepBios';

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
}));

function renderStep(
  overrides: {
    onBack?: () => void;
    onFinish?: () => void;
    onFinishAndGoTo?: (target: string) => void;
    finishing?: boolean;
  } = {},
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <StepBios
        onBack={overrides.onBack ?? vi.fn()}
        onFinish={overrides.onFinish ?? vi.fn()}
        onFinishAndGoTo={overrides.onFinishAndGoTo ?? vi.fn()}
        finishing={overrides.finishing ?? false}
      />
    </QueryClientProvider>,
  );
}

describe('StepBios', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows the present/required summary once loaded', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [
        {
          slug: 'ps1',
          name: 'PS1 BIOS',
          platform: 'ps1',
          bios_path: 'scph.bin',
          guidance_text: '',
          guidance_url: '',
          is_present: true,
          required: true,
        },
        {
          slug: 'saturn',
          name: 'Saturn BIOS',
          platform: 'saturn',
          bios_path: 'sat.bin',
          guidance_text: '',
          guidance_url: '',
          is_present: false,
          required: true,
        },
      ],
      total: 2,
      limit: 200,
      offset: 0,
    });
    renderStep();
    await waitFor(() => {
      expect(screen.getByText('1 of 2 required BIOS files present.')).toBeInTheDocument();
    });
  });

  it('calls onFinishAndGoTo with /emulators/bios when the finish-and-go button is clicked', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    const user = userEvent.setup();
    const onFinishAndGoTo = vi.fn();
    renderStep({ onFinishAndGoTo });
    await user.click(screen.getByRole('button', { name: 'Finish setup & go to BIOS →' }));
    expect(onFinishAndGoTo).toHaveBeenCalledWith('/emulators/bios');
  });

  it('calls onBack when Back is clicked', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    const user = userEvent.setup();
    const onBack = vi.fn();
    renderStep({ onBack });
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('calls onFinish when Finish is clicked', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    const user = userEvent.setup();
    const onFinish = vi.fn();
    renderStep({ onFinish });
    await user.click(screen.getByRole('button', { name: 'Finish' }));
    expect(onFinish).toHaveBeenCalledTimes(1);
  });

  it('shows a fallback message when the BIOS status request fails', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('network error'));
    renderStep();
    await waitFor(() => {
      expect(screen.getByText(/BIOS status could not be loaded/)).toBeInTheDocument();
    });
  });
});
