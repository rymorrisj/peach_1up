import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider } from '@/ui/ToastProvider';
import { apiFetch, ApiError } from '@/api/client';
import { FetchMetadataModal } from './FetchMetadataModal';
import {
  PREVIOUS_ASSETS_ERROR_TYPE,
  keepAddedNothing,
  previousAssetsCount,
} from './previousAssets';

// Accept All's previous-assets 409 (META-7): the modal shows a Replace /
// Keep choice with the server's count and retries with previous_assets set.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    rawDetail: unknown;
    constructor(status: number, detail: string, rawDetail?: unknown) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.rawDetail = rawDetail;
      this.name = 'ApiError';
    }
  },
}));

const DETAILS = {
  game_id: 5,
  title: 'Doom',
  release_date: '1993-12-10',
  overview: null,
  rating: null,
  cover_art_url: null,
  cover_art_thumb_url: null,
  genres: null,
  developer: null,
  publisher: null,
  video_urls: [],
  assets: [
    {
      url: 'https://cdn.thegamesdb.net/images/original/a.jpg',
      type: 'screenshot',
      thumb_url: null,
    },
  ],
};

const ACCEPT_URL = '/api/v1/game-items/1/accept-metadata-assets';

interface AcceptCall {
  previous_assets?: string;
}

type AcceptResponse = 'conflict' | 'ok' | 'ok-nothing-new' | 'ok-added' | 'too-many';

const TOO_MANY_DETAIL =
  'This metadata offers 31 images, but Accept All can apply at most 30 per apply (limit 30). Nothing was downloaded.';

function fetchedItems(count: number) {
  return { items: Array.from({ length: count }, (_, i) => ({ source_url: `https://x/${i}.jpg` })) };
}

function mockApi(acceptResponses: AcceptResponse[], existingCount = 3): AcceptCall[] {
  const acceptCalls: AcceptCall[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = typeof url === 'string' ? url : '';
    if (u.startsWith('/api/v1/game-items/metadata-search')) {
      return Promise.resolve({ results: [{ game_id: 5, title: 'Doom', release_date: '1993' }] });
    }
    if (u.startsWith('/api/v1/game-items/metadata-details')) return Promise.resolve(DETAILS);
    if (u === '/api/v1/game-items/enrich') return Promise.resolve({});
    if (u === ACCEPT_URL) {
      acceptCalls.push(JSON.parse(String(init?.body)) as AcceptCall);
      const next = acceptResponses.shift();
      if (next === 'conflict') {
        return Promise.reject(
          new ApiError(409, 'already has fetched images', {
            error_type: PREVIOUS_ASSETS_ERROR_TYPE,
            message: 'already has fetched images',
            existing_count: existingCount,
          }),
        );
      }
      if (next === 'too-many') return Promise.reject(new ApiError(413, TOO_MANY_DETAIL));
      if (next === 'ok-nothing-new') return Promise.resolve(fetchedItems(existingCount));
      if (next === 'ok-added') return Promise.resolve(fetchedItems(existingCount + 1));
      return Promise.resolve({});
    }
    return Promise.resolve({});
  });
  return acceptCalls;
}

function renderModal(onClose = vi.fn(), onSuccess = vi.fn()) {
  sessionStorage.clear();
  render(
    <ToastProvider>
      <FetchMetadataModal
        open
        onClose={onClose}
        entityType="game_item_bundle"
        entityId={1}
        entityTitle="Doom"
        storageKey="test-fetch-metadata"
        onSuccess={onSuccess}
        activeProviderLabel="TheGamesDB"
      />
    </ToastProvider>,
  );
  return { onClose, onSuccess };
}

async function reachAcceptAll(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Search' }));
  await user.click(await screen.findByRole('radio', { name: /Doom/ }));
  await user.click(screen.getByRole('button', { name: 'Fetch Now' }));
  await user.click(await screen.findByRole('button', { name: 'Keep' }));
  await screen.findByRole('button', { name: 'Accept All' });
}

describe('FetchMetadataModal previous assets choice', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows Replace and Keep with the count on a previous-assets 409', async () => {
    const user = userEvent.setup();
    const acceptCalls = mockApi(['conflict']);
    renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));

    const choice = await screen.findByRole('alertdialog', { name: 'Previously fetched images' });
    expect(choice).toHaveTextContent('already has 3 fetched images');
    expect(choice).toHaveTextContent('Media you added yourself is never touched.');
    expect(screen.getByRole('button', { name: 'Replace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Keep and add new' })).toBeInTheDocument();
    expect(acceptCalls).toHaveLength(1);
    expect(acceptCalls[0].previous_assets).toBeUndefined();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each([
    ['Replace', 'replace'],
    ['Keep and add new', 'keep'],
  ])('%s retries with previous_assets=%s and closes on success', async (label, value) => {
    const user = userEvent.setup();
    const acceptCalls = mockApi(['conflict', 'ok']);
    const { onClose, onSuccess } = renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));
    await user.click(await screen.findByRole('button', { name: label }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(acceptCalls).toHaveLength(2);
    expect(acceptCalls[1].previous_assets).toBe(value);
    expect(onSuccess).toHaveBeenCalled();
  });

  it('Back returns to Accept All without sending anything', async () => {
    const user = userEvent.setup();
    const acceptCalls = mockApi(['conflict']);
    renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));
    await user.click(await screen.findByRole('button', { name: 'Back' }));

    expect(screen.getByRole('button', { name: 'Accept All' })).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(acceptCalls).toHaveLength(1);
  });

  it('Keep and add new with nothing new says so instead of "Linked media created"', async () => {
    const user = userEvent.setup();
    mockApi(['conflict', 'ok-nothing-new']);
    const { onClose } = renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));
    await user.click(await screen.findByRole('button', { name: 'Keep and add new' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await screen.findByText('No new media to add')).toBeInTheDocument();
    expect(screen.queryByText(/Linked media created/)).not.toBeInTheDocument();
  });

  it('Keep and add new that adds images still says "Linked media created"', async () => {
    const user = userEvent.setup();
    mockApi(['conflict', 'ok-added']);
    const { onClose } = renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));
    await user.click(await screen.findByRole('button', { name: 'Keep and add new' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await screen.findByText(/Linked media created/)).toBeInTheDocument();
    expect(screen.queryByText('No new media to add')).not.toBeInTheDocument();
  });

  it('shows the over-the-cap 413 as readable text in the modal', async () => {
    const user = userEvent.setup();
    mockApi(['too-many']);
    const { onClose } = renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(TOO_MANY_DETAIL);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('a first apply sends no previous_assets', async () => {
    const user = userEvent.setup();
    const acceptCalls = mockApi(['ok']);
    const { onClose } = renderModal();

    await reachAcceptAll(user);
    await user.click(screen.getByRole('button', { name: 'Accept All' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(acceptCalls).toEqual([{ assets: DETAILS.assets }]);
  });
});

describe('previousAssetsCount', () => {
  it('reads existing_count from the structured 409', () => {
    const err = new ApiError(409, 'x', {
      error_type: PREVIOUS_ASSETS_ERROR_TYPE,
      existing_count: 4,
    });
    expect(previousAssetsCount(err)).toBe(4);
  });

  it('ignores other 409s and other errors', () => {
    expect(
      previousAssetsCount(new ApiError(409, 'An Accept All for this game is already running.')),
    ).toBeNull();
    expect(
      previousAssetsCount(new ApiError(422, 'x', { error_type: PREVIOUS_ASSETS_ERROR_TYPE })),
    ).toBeNull();
    expect(previousAssetsCount(new Error('network'))).toBeNull();
  });
});

describe('keepAddedNothing', () => {
  const bundle = (fetched: number, manual = 1) => ({
    items: [
      ...Array.from({ length: fetched }, () => ({ source_url: 'https://x/a.jpg' })),
      ...Array.from({ length: manual }, () => ({ source_url: null })),
    ],
  });

  it('is true when Keep leaves the fetched count unchanged', () => {
    expect(keepAddedNothing('keep', 3, bundle(3))).toBe(true);
  });

  it('is false when Keep adds fetched images', () => {
    expect(keepAddedNothing('keep', 3, bundle(4))).toBe(false);
  });

  it('is false for Replace, a first apply, or an unknown prior count', () => {
    expect(keepAddedNothing('replace', 3, bundle(3))).toBe(false);
    expect(keepAddedNothing(undefined, null, bundle(3))).toBe(false);
    expect(keepAddedNothing('keep', null, bundle(3))).toBe(false);
  });
});
