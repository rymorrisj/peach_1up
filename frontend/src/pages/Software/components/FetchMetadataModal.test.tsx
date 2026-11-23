import { useState } from 'react';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { apiFetch, ApiError } from '@/api/client';
import { renderWithProviders } from '@/test/helpers';
import { RATING_CHANGE_ERROR_TYPE } from '@/hooks/useRatingChangeConfirm';
import type { MetadataJobStatus } from '@/hooks/useMetadataApplyJob';
import { FetchMetadataModal } from './FetchMetadataModal';
import { PREVIOUS_ASSETS_ERROR_TYPE } from './previousAssets';
import type { GameItemBundleData } from './CollectionCard';

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

const SEARCH = '/api/v1/game-items/metadata-search';
const DETAILS_URL = '/api/v1/game-items/metadata-details';
const ENRICH = '/api/v1/game-items/enrich';
const ACCEPT = '/api/v1/game-items/1/accept-metadata-assets';
const JOB = '/api/v1/game-items/metadata-jobs/j1';

const asset = (type: string, n: number) => ({
  url: `https://cdn.thegamesdb.net/${type}-${n}.jpg`,
  type,
  thumb_url: `https://cdn.thegamesdb.net/thumb/${type}-${n}.jpg`,
});

const SMALL_ASSETS = [
  asset('boxart_front', 1),
  asset('boxart_back', 1),
  asset('clearlogo', 1),
  asset('banner', 1),
  ...Array.from({ length: 5 }, (_, i) => asset('screenshot', i + 1)),
  asset('fanart', 1),
  asset('fanart', 2),
];

const DETAILS = {
  game_id: 5,
  title: 'Doom (1993)',
  release_date: '1993-12-10',
  overview: 'A classic.',
  rating: 'M - Mature 17+',
  genres: ['Action'],
  developer: 'id Software',
  publisher: 'id Software',
  external_links: [
    { type: 'trailer', url: 'https://youtu.be/abc', source: 'provider' },
    { type: 'official', url: 'https://doom.example/', source: 'provider' },
  ],
  assets: SMALL_ASSETS,
};

const NO_ASSETS = { ...DETAILS, assets: [] };

function makeBundle(overrides: Record<string, unknown> = {}): GameItemBundleData {
  return {
    id: 1,
    slug: 'doom',
    title: 'Doom',
    description: null,
    year: null,
    genres: [],
    developer: null,
    publisher: null,
    content_rating: null,
    metadata_fetched_at: null,
    external_game_id: null,
    external_provider: null,
    external_links: null,
    tags: [],
    linked_items: [],
    ...overrides,
  } as unknown as GameItemBundleData;
}

const job = (patch: Partial<MetadataJobStatus>): MetadataJobStatus => ({
  job_id: 'j1',
  state: 'running',
  done: 0,
  total: 3,
  label: null,
  error: null,
  cancel_requested: false,
  ...patch,
});

interface Call {
  url: string;
  method: string;
  body: Record<string, unknown> | undefined;
  timeoutMs: number | undefined;
}

interface ApiScript {
  details?: unknown;
  search?: () => Promise<unknown>;
  enrich?: (n: number) => Promise<unknown>;
  accept?: (n: number) => Promise<unknown>;
  statuses?: MetadataJobStatus[];
}

function mockApi(script: ApiScript = {}): Call[] {
  const calls: Call[] = [];
  const statuses = [...(script.statuses ?? [job({ state: 'done', done: 3 })])];
  vi.mocked(apiFetch).mockImplementation(((
    url: unknown,
    init?: RequestInit & { timeoutMs?: number },
  ) => {
    const u = String(url);
    const call: Call = {
      url: u,
      method: init?.method ?? 'GET',
      body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined,
      timeoutMs: init?.timeoutMs,
    };
    calls.push(call);
    const count = (target: string, method: string) =>
      calls.filter((c) => c.url === target && c.method === method).length;
    if (u.startsWith(SEARCH)) {
      return (
        script.search?.() ??
        Promise.resolve({
          results: [{ game_id: 5, title: 'Doom', release_date: '1993', platform: 'PC' }],
        })
      );
    }
    if (u.startsWith(DETAILS_URL)) return Promise.resolve(script.details ?? DETAILS);
    if (u === ENRICH) return script.enrich?.(count(ENRICH, 'POST')) ?? Promise.resolve({});
    if (u === ACCEPT) {
      return script.accept?.(count(ACCEPT, 'POST')) ?? Promise.resolve({ job_id: 'j1' });
    }
    if (u === `${JOB}/cancel`) return Promise.resolve(job({ cancel_requested: true }));
    if (u === JOB) return Promise.resolve(statuses.length > 1 ? statuses.shift() : statuses[0]);
    return Promise.resolve({});
  }) as typeof apiFetch);
  return calls;
}

const rejectWith = (status: number, detail: string, raw?: unknown) =>
  Promise.reject(new ApiError(status, detail, raw));

const conflict409 = (existing = 3) =>
  rejectWith(409, 'already has fetched images', {
    error_type: PREVIOUS_ASSETS_ERROR_TYPE,
    message: 'already has fetched images',
    existing_count: existing,
  });

const ratingConflict409 = (reason = 'lowered') =>
  rejectWith(409, 'rating change', {
    error_type: RATING_CHANGE_ERROR_TYPE,
    reason,
    current_rating: 'M',
    new_rating: 'E',
    message: 'rating change',
  });

interface HarnessProps {
  bundle?: GameItemBundleData;
  knownMatchId?: number | null;
  onSuccess?: () => void;
  onClose?: () => void;
}

function Harness({ bundle, knownMatchId = null, onSuccess = vi.fn(), onClose }: HarnessProps) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        reopen
      </button>
      <FetchMetadataModal
        open={open}
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
        bundle={bundle ?? makeBundle()}
        storageKey="test-fetch-metadata"
        knownMatchId={knownMatchId}
        onSuccess={onSuccess}
        activeProviderLabel="TheGamesDB"
      />
    </>
  );
}

function renderModal(props: HarnessProps = {}) {
  sessionStorage.clear();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const onSuccess = props.onSuccess ?? vi.fn();
  const onClose = props.onClose ?? vi.fn();
  renderWithProviders(<Harness {...props} onSuccess={onSuccess} onClose={onClose} />);
  return { user, onSuccess, onClose };
}

type User = ReturnType<typeof userEvent.setup>;

async function reachReview(user: User) {
  await user.click(screen.getByRole('button', { name: 'Search' }));
  await user.click(await screen.findByRole('radio', { name: /Doom/ }));
  await user.click(screen.getByRole('button', { name: 'Fetch Now' }));
  await screen.findByRole('button', { name: 'Apply' });
}

const tick = (ms = 1000) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

const inlineAlert = () =>
  screen.queryAllByRole('alert').find((el) => el.querySelector('button') === null);

const enrichBody = (calls: Call[]) => calls.find((c) => c.url === ENRICH)?.body;
const acceptCalls = (calls: Call[]) => calls.filter((c) => c.url === ACCEPT);

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

describe('step flow', () => {
  it('goes Search, Review, Apply', async () => {
    const calls = mockApi({ statuses: [job({ state: 'running', done: 1 })] });
    const { user } = renderModal();

    expect(screen.getByText('Step 1 of 3: Search')).toBeInTheDocument();
    await reachReview(user);
    expect(screen.getByText('Step 2 of 3: Review')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(await screen.findByText('Step 3 of 3: Apply')).toBeInTheDocument();
    expect(acceptCalls(calls)).toHaveLength(1);
  });

  it('searches and fetches details with the 90 second timeout', async () => {
    const calls = mockApi();
    const { user } = renderModal();
    await reachReview(user);

    const lookups = calls.filter((c) => c.url.startsWith(SEARCH) || c.url.startsWith(DETAILS_URL));
    expect(lookups).toHaveLength(2);
    for (const c of lookups) expect(c.timeoutMs).toBe(90_000);
  });

  it('skips Search for a stored provider match and offers Search again', async () => {
    const calls = mockApi();
    const { user } = renderModal({ knownMatchId: 5 });

    expect(await screen.findByRole('button', { name: 'Apply' })).toBeInTheDocument();
    expect(calls.some((c) => c.url.startsWith(SEARCH))).toBe(false);
    expect(calls.find((c) => c.url.startsWith(DETAILS_URL))?.url).toContain('game_id=5');

    await user.click(screen.getByRole('button', { name: 'Wrong match? Search again' }));
    expect(screen.getByText('Step 1 of 3: Search')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
  });

  it('opens on Search when no provider match is stored', async () => {
    const calls = mockApi();
    renderModal({ knownMatchId: null });

    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('shows a failed stored-match lookup with Retry and Search instead', async () => {
    mockApi({ details: undefined });
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new ApiError(504, 'TheGamesDB did not respond in time.'),
    );
    const { user } = renderModal({ knownMatchId: 5 });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'TheGamesDB did not respond in time.',
    );
    expect(screen.getByRole('button', { name: 'Search instead' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Search instead' }));
    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
  });

  it('shows the server message for a failed search inline', async () => {
    mockApi({ search: () => rejectWith(502, 'Could not reach TheGamesDB.') });
    const { user } = renderModal();

    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach TheGamesDB.');
  });

  it('shows the search platform label on results', async () => {
    mockApi();
    const { user } = renderModal();
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('PC')).toBeInTheDocument();
  });
});

describe('previously fetched notice', () => {
  it('shows the last fetch time inline instead of a native confirm', async () => {
    mockApi();
    const confirmSpy = vi.spyOn(window, 'confirm');
    renderModal({ bundle: makeBundle({ metadata_fetched_at: '2026-01-02T03:04:05' }) });

    const note = screen.getByRole('note');
    expect(note).toHaveTextContent('Metadata was last fetched on');
    expect(note).toHaveTextContent('additional provider API credits');
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('shows no notice for a game that was never fetched', () => {
    mockApi();
    renderModal();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});

describe('review fields', () => {
  const bundle = makeBundle({ developer: 'Old Dev' });

  it('starts empty fields checked and fields with a different value unchecked', async () => {
    mockApi({ details: NO_ASSETS });
    const { user } = renderModal({ bundle });
    await reachReview(user);

    for (const name of ['Release year', 'Description', 'Genres', 'Publisher', 'Links']) {
      expect(screen.getByRole('checkbox', { name })).toBeChecked();
    }
    for (const name of ['Title', 'Developer']) {
      expect(screen.getByRole('checkbox', { name })).not.toBeChecked();
    }
  });

  it('shows current against fetched values', async () => {
    mockApi({ details: NO_ASSETS });
    const { user } = renderModal({ bundle });
    await reachReview(user);

    const row = screen.getByRole('checkbox', { name: 'Developer' }).closest('li') as HTMLElement;
    expect(within(row).getByText('Old Dev')).toBeInTheDocument();
    expect(within(row).getByText('id Software')).toBeInTheDocument();
  });

  it('sends only the checked fields, and toggles change what is sent', async () => {
    const calls = mockApi({ details: NO_ASSETS });
    const { user } = renderModal({ bundle });
    await reachReview(user);

    await user.click(screen.getByRole('checkbox', { name: 'Title' }));
    await user.click(screen.getByRole('checkbox', { name: 'Genres' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(enrichBody(calls)).toBeDefined());
    const body = enrichBody(calls)!;
    expect(body).toMatchObject({
      entity_type: 'game_item_bundle',
      entity_id: 1,
      metadata_source: 'TheGamesDB',
      external_game_id: 5,
      title: 'Doom (1993)',
      year: 1993,
      description: 'A classic.',
      publisher: 'id Software',
    });
    expect(body).not.toHaveProperty('developer');
    expect(body).not.toHaveProperty('genre');
    expect(body).not.toHaveProperty('cover_art_url');
    expect(body).not.toHaveProperty('entity_type', 'game_item');
  });

  it('shows the unresolved genre warning', async () => {
    mockApi({ details: { ...NO_ASSETS, unresolved_genre_ids: [99, 100] } });
    const { user } = renderModal({ bundle });
    await reachReview(user);

    const warning = screen.getByRole('alert');
    expect(warning).toHaveTextContent('2 genres could not be matched');
    expect(warning).toHaveTextContent('99, 100');
  });

  it('closes with a toast and sends no job when no image is selected', async () => {
    const calls = mockApi({ details: NO_ASSETS });
    const { user, onSuccess, onClose } = renderModal({ bundle });
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onSuccess).toHaveBeenCalled();
    expect(await screen.findByText('Metadata applied: Doom (1993)')).toBeInTheDocument();
    expect(acceptCalls(calls)).toHaveLength(0);
  });

  it('disables Apply when nothing is selected', async () => {
    mockApi({ details: NO_ASSETS });
    const { user } = renderModal({ bundle });
    await reachReview(user);

    for (const name of [
      'Release year',
      'Description',
      'Genres',
      'Publisher',
      'Links',
      'Content rating',
    ]) {
      const box = screen.getByRole('checkbox', { name });
      if (box.getAttribute('aria-checked') === 'true') await user.click(box);
    }
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
    expect(screen.getByText('Nothing is selected to apply.')).toBeInTheDocument();
  });
});

describe('rating row', () => {
  it('shows the normalised rating, not the raw provider value', async () => {
    mockApi({ details: NO_ASSETS });
    const { user } = renderModal();
    await reachReview(user);

    const row = screen
      .getByRole('checkbox', { name: 'Content rating' })
      .closest('li') as HTMLElement;
    expect(row).toHaveTextContent('M (from "M - Mature 17+")');
  });

  it('shows the 409 inline in the rating row, with the reason, and applies nothing until confirmed', async () => {
    const calls = mockApi({
      details: NO_ASSETS,
      enrich: (n) => (n === 1 ? ratingConflict409('lowered') : Promise.resolve({})),
    });
    const { user, onSuccess } = renderModal({
      bundle: makeBundle({ content_rating: 'M' }),
    });
    await reachReview(user);
    const rating = screen.getByRole('checkbox', { name: 'Content rating' });
    if (rating.getAttribute('aria-checked') !== 'true') await user.click(rating);
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    const alert = await screen.findByText(/Nothing was applied\. This lowers the current rating/);
    const row = alert.closest('li') as HTMLElement;
    expect(row).toHaveTextContent('Currently M, would become E');
    expect(onSuccess).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();

    await user.click(within(row).getByRole('checkbox', { name: /I understand/ }));
    expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(calls.filter((c) => c.url === ENRICH)).toHaveLength(2));
    const retry = calls.filter((c) => c.url === ENRICH)[1].body!;
    expect(retry).toMatchObject({ content_rating: 'M - Mature 17+', confirm_rating_change: true });
    expect(onSuccess).toHaveBeenCalled();
  });

  it('skips the rating by omitting the key when the row is unchecked', async () => {
    const calls = mockApi({
      details: NO_ASSETS,
      enrich: (n) => (n === 1 ? ratingConflict409('cleared') : Promise.resolve({})),
    });
    const { user } = renderModal({ bundle: makeBundle({ content_rating: 'M' }) });
    await reachReview(user);
    const rating = screen.getByRole('checkbox', { name: 'Content rating' });
    if (rating.getAttribute('aria-checked') !== 'true') await user.click(rating);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText(/Nothing was applied/);

    await user.click(screen.getByRole('checkbox', { name: 'Content rating' }));
    expect(screen.queryByText(/Nothing was applied/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(calls.filter((c) => c.url === ENRICH)).toHaveLength(2));
    const second = calls.filter((c) => c.url === ENRICH)[1].body!;
    expect(second).not.toHaveProperty('content_rating');
    expect(second).not.toHaveProperty('confirm_rating_change');
  });
});

describe('links row', () => {
  it('sends external_links with the enrich call when checked', async () => {
    const calls = mockApi({ details: NO_ASSETS });
    const { user } = renderModal();
    await reachReview(user);

    expect(screen.getByRole('checkbox', { name: 'Links' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(enrichBody(calls)).toBeDefined());
    expect(enrichBody(calls)?.external_links).toEqual(DETAILS.external_links);
  });

  it('omits external_links when unchecked', async () => {
    const calls = mockApi({ details: NO_ASSETS });
    const { user } = renderModal();
    await reachReview(user);

    await user.click(screen.getByRole('checkbox', { name: 'Links' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(enrichBody(calls)).toBeDefined());
    expect(enrichBody(calls)).not.toHaveProperty('external_links');
  });
});

describe('assets', () => {
  it('shows thumb_url images grouped by type with the default selection', async () => {
    mockApi();
    const { user } = renderModal();
    await reachReview(user);

    expect(screen.getByText('11 of 30 selected')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Screenshots' })).toBeInTheDocument();
    expect(screen.getByAltText('Front box art 1')).toHaveAttribute(
      'src',
      'https://cdn.thegamesdb.net/thumb/boxart_front-1.jpg',
    );
    for (const name of [
      'Front box art 1',
      'Back box art 1',
      'Clear logo 1',
      'Banner 1',
      'Screenshot 3',
      'Fanart 2',
    ]) {
      expect(screen.getByRole('checkbox', { name: `Include ${name}` })).toBeChecked();
    }
    expect(screen.getByRole('checkbox', { name: 'Include Screenshot 5' })).toBeChecked();
  });

  it('stops further selection at 30', async () => {
    mockApi({
      details: {
        ...DETAILS,
        assets: [
          asset('boxart_front', 1),
          ...Array.from({ length: 35 }, (_, i) => asset('screenshot', i + 1)),
        ],
      },
    });
    const { user } = renderModal();
    await reachReview(user);

    expect(screen.getByText('30 of 30 selected')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Include Screenshot 30' })).toBeDisabled();

    await user.click(screen.getByRole('checkbox', { name: 'Include Screenshot 1' }));
    expect(screen.getByText('29 of 30 selected')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Include Screenshot 30' })).toBeEnabled();
  });

  it('sends only the selected assets', async () => {
    const calls = mockApi();
    const { user } = renderModal();
    await reachReview(user);

    await user.click(screen.getByRole('checkbox', { name: 'Include Banner 1' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');

    const urls = (acceptCalls(calls)[0].body?.assets as { url: string }[]).map((a) => a.url);
    expect(urls).toHaveLength(10);
    expect(urls).not.toContain(asset('banner', 1).url);
  });

  it('defaults the cover to front box art and sends it as cover_asset_url', async () => {
    const calls = mockApi();
    const { user } = renderModal();
    await reachReview(user);

    expect(screen.getByRole('radio', { name: /Cover Front box art 1/ })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    expect(acceptCalls(calls)[0].body?.cover_asset_url).toBe(asset('boxart_front', 1).url);
  });

  it('sends the picked cover, and none when the cover is left alone', async () => {
    const calls = mockApi();
    const { user } = renderModal();
    await reachReview(user);

    await user.click(screen.getByRole('radio', { name: /Cover Screenshot 2/ }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    expect(acceptCalls(calls)[0].body?.cover_asset_url).toBe(asset('screenshot', 2).url);
  });

  it('omits cover_asset_url when "Leave the game cover as it is" is chosen', async () => {
    const calls = mockApi();
    const { user } = renderModal();
    await reachReview(user);

    await user.click(screen.getByRole('radio', { name: 'Leave the game cover as it is' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    expect(acceptCalls(calls)[0].body).not.toHaveProperty('cover_asset_url');
  });

  it('moves the cover off an image that is deselected', async () => {
    const calls = mockApi({
      details: {
        ...DETAILS,
        assets: [asset('boxart_front', 1), asset('cover', 1), asset('screenshot', 1)],
      },
    });
    const { user } = renderModal();
    await reachReview(user);

    await user.click(screen.getByRole('checkbox', { name: 'Include Front box art 1' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    expect(acceptCalls(calls)[0].body?.cover_asset_url).toBe(asset('cover', 1).url);
  });

  it('shows the 413 over-the-cap message as readable text', async () => {
    const message =
      'This metadata offers 31 images, but Accept All can apply at most 30 per apply (limit 30). Nothing was downloaded.';
    mockApi({ accept: () => rejectWith(413, message) });
    const { user, onClose } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('Replace or Keep', () => {
  it('shows the choice with the server count on a previous-assets 409', async () => {
    const calls = mockApi({ accept: () => conflict409(3) });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    const panel = await screen.findByRole('alertdialog', { name: 'Previously fetched images' });
    expect(panel).toHaveTextContent('already has 3 fetched images');
    expect(panel).toHaveTextContent('Media you added yourself is never touched.');
    expect(panel).toHaveTextContent('the game cover is then set to the image you chose');
    expect(screen.getByRole('button', { name: 'Replace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Keep and add new' })).toBeInTheDocument();
    expect(acceptCalls(calls)[0].body).not.toHaveProperty('previous_assets');
    expect(screen.queryByText('Step 3 of 3: Apply')).not.toBeInTheDocument();
  });

  it.each([
    ['Replace', 'replace'],
    ['Keep and add new', 'keep'],
  ])('%s retries with previous_assets=%s and moves to Apply', async (label, value) => {
    const calls = mockApi({
      accept: (n) => (n === 1 ? conflict409() : Promise.resolve({ job_id: 'j1' })),
    });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await user.click(await screen.findByRole('button', { name: label }));

    expect(await screen.findByText('Step 3 of 3: Apply')).toBeInTheDocument();
    expect(acceptCalls(calls)).toHaveLength(2);
    expect(acceptCalls(calls)[1].body?.previous_assets).toBe(value);
  });

  it('Back returns to Review without sending anything more', async () => {
    const calls = mockApi({ accept: () => conflict409() });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await user.click(await screen.findByRole('button', { name: 'Back' }));

    expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(acceptCalls(calls)).toHaveLength(1);
  });
});

describe('apply job', () => {
  it('shows per-asset progress from the status poll, then completes', async () => {
    const onSuccess = vi.fn();
    mockApi({
      statuses: [
        job({ state: 'running', done: 1, total: 3, label: 'screenshot (2 of 3)' }),
        job({ state: 'running', done: 2, total: 3, label: 'fanart (3 of 3)' }),
        job({ state: 'done', done: 3, total: 3 }),
      ],
    });
    const { user } = renderModal({ onSuccess });
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    onSuccess.mockClear();

    await tick();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
    expect(screen.getByText(/1 of 3 images, screenshot \(2 of 3\)/)).toBeInTheDocument();

    await tick();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '2');

    await tick();
    expect(await screen.findByText('Added 3 of 3')).toBeInTheDocument();
    expect(await screen.findByText('Fetched images added to "Doom".')).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('says "No new media to add" when the job created nothing', async () => {
    mockApi({ statuses: [job({ state: 'done', done: 0, total: 2 })] });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    await tick();

    expect(await screen.findAllByText('No new media to add')).not.toHaveLength(0);
    expect(screen.queryByText(/Fetched images added/)).not.toBeInTheDocument();
  });

  it('shows the server failure message verbatim with Retry, and Retry starts the job again', async () => {
    const message = 'TheGamesDB server returned 503. Nothing was added.';
    const calls = mockApi({
      statuses: [job({ state: 'failed', done: 1, error: { code: 'provider_error', message } })],
    });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    await tick();

    // Toasts are role="alert" too (with a Dismiss button); the inline one has none.
    await waitFor(() => expect(inlineAlert()).toBeDefined());
    const alert = inlineAlert()!;
    expect(alert.textContent).toBe(message);
    expect(screen.queryByText(/timed out/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(acceptCalls(calls)).toHaveLength(2));
    expect(await screen.findByText('Step 3 of 3: Apply')).toBeInTheDocument();
  });

  it('offers Cancel while running and posts to the cancel route', async () => {
    const calls = mockApi({
      statuses: [job({ state: 'running', done: 1 }), job({ state: 'cancelled', done: 1 })],
    });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    await tick();

    await user.click(screen.getByRole('button', { name: 'Cancel apply' }));
    expect(calls.some((c) => c.url === `${JOB}/cancel` && c.method === 'POST')).toBe(true);

    await tick();
    expect(await screen.findAllByText('Cancelled. Nothing was added.')).not.toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Cancel apply' })).not.toBeInTheDocument();
  });

  it('lets the user close while it runs, keeps polling, and toasts on completion', async () => {
    const onSuccess = vi.fn();
    const calls = mockApi({
      statuses: [job({ state: 'running', done: 1 }), job({ state: 'done', done: 3 })],
    });
    const { user, onClose } = renderModal({ onSuccess });
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    onSuccess.mockClear();

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await tick();
    await tick();
    expect(calls.filter((c) => c.url === JOB).length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByText('Fetched images added to "Doom".')).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('reopens on the running job instead of starting over', async () => {
    mockApi({ statuses: [job({ state: 'running', done: 1 })] });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    await user.click(screen.getByRole('button', { name: 'Close' }));

    await user.click(screen.getByRole('button', { name: 'reopen' }));
    expect(await screen.findByText('Step 3 of 3: Apply')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('reports a failure toast when the job fails after the modal was closed', async () => {
    mockApi({
      statuses: [
        job({
          state: 'failed',
          error: { code: 'disk_full', message: 'The disk is full. Nothing was added.' },
        }),
      ],
    });
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');
    await user.click(screen.getByRole('button', { name: 'Close' }));

    await tick();
    expect(await screen.findByText('The disk is full. Nothing was added.')).toBeInTheDocument();
  });

  it('no longer sends the old per-disc or accept-timeout call shapes', async () => {
    const calls = mockApi();
    const { user } = renderModal();
    await reachReview(user);
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await screen.findByText('Step 3 of 3: Apply');

    const accept = acceptCalls(calls)[0];
    expect(accept.timeoutMs).toBeUndefined();
    for (const c of calls.filter((x) => x.url === ENRICH)) {
      expect(c.body).not.toHaveProperty('cover_art_url');
      expect(c.body?.entity_type).toBe('game_item_bundle');
    }
  });
});
