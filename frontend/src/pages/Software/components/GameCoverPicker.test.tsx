import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import { GameCoverPicker, type CoverCandidate } from './GameCoverPicker';

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

const LIST_URL = '/api/v1/game-item-bundle/7/cover-candidates';
const SET_URL = '/api/v1/game-item-bundle/7/cover-art';
const CLEAR_URL = '/api/v1/game-item-bundle/7/items/101';

function candidate(id: number, overrides: Partial<CoverCandidate> = {}): CoverCandidate {
  return {
    media_item_id: id,
    title: `Shot ${id}`,
    asset_type: 'screenshot',
    file_url: `/media/media/${id}.png`,
    media_item_bundle_id: 1,
    is_current: false,
    ...overrides,
  };
}

function setup(candidates: CoverCandidate[], onSet?: () => unknown) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = String(url);
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({
      url: u,
      method,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    });
    if (u === LIST_URL) return Promise.resolve(candidates);
    if (u === SET_URL)
      return Promise.resolve().then(onSet ?? (() => ({ cover_art_path: 'C:/lib/1.png' })));
    return Promise.resolve({});
  });
  return calls;
}

function renderPicker(
  props: { hasCover?: boolean; onCoverChanged?: (p: string | null) => void } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GameCoverPicker
        bundleId={7}
        displayDiscId={101}
        hasCover={props.hasCover ?? true}
        detailQueryKey={['game', 'detail', 'doom']}
        onCoverChanged={props.onCoverChanged ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

describe('GameCoverPicker', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders nothing when no linked image can be used', async () => {
    setup([]);
    const { container } = renderPicker();

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('shows titled thumbnails and marks the current cover', async () => {
    setup([candidate(1, { is_current: true }), candidate(2)]);
    renderPicker();

    expect(await screen.findByText('Shot 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use Shot 1 as cover art' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Use Shot 2 as cover art' })).toBeEnabled();
    expect(screen.getByText('Cover art')).toBeInTheDocument();
  });

  it('sets the clicked image and reports the stored path', async () => {
    const user = userEvent.setup();
    const onCoverChanged = vi.fn();
    const calls = setup([candidate(1), candidate(2)]);
    renderPicker({ onCoverChanged });

    await user.click(await screen.findByRole('button', { name: 'Use Shot 2 as cover art' }));

    await waitFor(() => expect(onCoverChanged).toHaveBeenCalledWith('C:/lib/1.png'));
    expect(calls.find((c) => c.url === SET_URL)).toMatchObject({
      method: 'PUT',
      body: { media_item_id: 2 },
    });
  });

  it('clears the display disc cover with an explicit null', async () => {
    const user = userEvent.setup();
    const onCoverChanged = vi.fn();
    const calls = setup([candidate(1)]);
    renderPicker({ onCoverChanged });

    await user.click(await screen.findByRole('button', { name: 'Clear cover' }));

    await waitFor(() => expect(onCoverChanged).toHaveBeenCalledWith(null));
    expect(calls.find((c) => c.url === CLEAR_URL)).toMatchObject({
      method: 'PATCH',
      body: { cover_art_path: null },
    });
  });

  it('hides Clear when the display disc has no cover', async () => {
    setup([candidate(1)]);
    renderPicker({ hasCover: false });

    await screen.findByText('Shot 1');
    expect(screen.queryByRole('button', { name: 'Clear cover' })).not.toBeInTheDocument();
  });

  it('shows the server message when setting fails and does not report a change', async () => {
    const user = userEvent.setup();
    const onCoverChanged = vi.fn();
    setup([candidate(1)], () => {
      throw new ApiError(404, 'Media item not found.');
    });
    renderPicker({ onCoverChanged });

    await user.click(await screen.findByRole('button', { name: 'Use Shot 1 as cover art' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Media item not found.');
    expect(onCoverChanged).not.toHaveBeenCalled();
  });
});
