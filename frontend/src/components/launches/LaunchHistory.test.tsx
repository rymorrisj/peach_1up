import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/helpers';
import LaunchHistory from '@/components/launches/LaunchHistory';
import { apiFetch } from '@/api/client';
import type { components } from '@shared/types';

type LaunchHistoryRead = components['schemas']['LaunchHistoryRead'];

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

const COMPLETED_LAUNCH: LaunchHistoryRead = {
  id: 101,
  target_type: 'software_collection',
  emulator_slug: 'dosbox',
  network_blocked: true,
  job_isolated: false,
  sandboxed: false,
  started_at: '2024-03-15T10:30:00',
  ended_at: '2024-03-15T11:00:00',
  exit_code: 0,
  software_collection_id: 1,
};

const RUNNING_LAUNCH: LaunchHistoryRead = {
  id: 102,
  target_type: 'software_collection',
  emulator_slug: 'dosbox',
  network_blocked: true,
  job_isolated: false,
  sandboxed: false,
  started_at: '2024-03-15T12:00:00',
  ended_at: null,
  software_collection_id: 1,
};

describe('LaunchHistory', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders nothing when the API returns an empty list', async () => {
    vi.mocked(apiFetch).mockResolvedValue([]);
    const { container } = renderWithProviders(
      <LaunchHistory targetId={1} targetType="software_collection" />,
    );
    await waitFor(() => {
      expect(vi.mocked(apiFetch)).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
  });

  it('renders launch rows when the API returns launches', async () => {
    vi.mocked(apiFetch).mockResolvedValue([COMPLETED_LAUNCH]);
    renderWithProviders(<LaunchHistory targetId={1} targetType="software_collection" />);
    // The component shows start and end date strings; both contain the year
    await waitFor(() => {
      expect(screen.getAllByText(/2024/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows "running" for a launch with no ended_at', async () => {
    vi.mocked(apiFetch).mockResolvedValue([RUNNING_LAUNCH]);
    renderWithProviders(<LaunchHistory targetId={1} targetType="software_collection" />);
    await waitFor(() => {
      expect(screen.getByText('running')).toBeInTheDocument();
    });
  });
});
