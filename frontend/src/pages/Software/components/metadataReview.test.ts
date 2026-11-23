import {
  ASSET_LIMIT,
  buildEnrichPayload,
  buildReviewFields,
  countCheckedItems,
  defaultAssetSelection,
  defaultCoverUrl,
  defaultFieldSelection,
  defaultRatingSelected,
  normalizeContentRating,
  uniqueAssets,
  type CurrentMetadata,
  type GameDetails,
  type MetadataAsset,
} from './metadataReview';

const CURRENT: CurrentMetadata = {
  title: 'Doom',
  year: null,
  description: null,
  genres: [],
  developer: 'Old Dev',
  publisher: null,
  content_rating: null,
};

const DETAILS: GameDetails = {
  game_id: 5,
  title: 'Doom (1993)',
  release_date: '1993-12-10',
  overview: 'A classic.',
  rating: 'M - Mature 17+',
  genres: ['Action'],
  developer: 'id Software',
  publisher: 'id Software',
  external_links: [{ type: 'trailer', url: 'https://youtu.be/abc' }],
  assets: [],
};

const asset = (type: string, n: number): MetadataAsset => ({
  url: `https://cdn.thegamesdb.net/${type}-${n}.jpg`,
  type,
  thumb_url: null,
});

describe('field defaults', () => {
  it('starts empty fields checked and fields holding a different value unchecked', () => {
    const fields = buildReviewFields(CURRENT, DETAILS);
    expect(defaultFieldSelection(fields)).toEqual({
      title: false,
      year: true,
      description: true,
      genre: true,
      developer: false,
      publisher: true,
    });
  });

  it('starts a field whose value already matches checked', () => {
    const fields = buildReviewFields({ ...CURRENT, title: 'Doom (1993)' }, DETAILS);
    expect(defaultFieldSelection(fields).title).toBe(true);
  });

  it('compares genres as a set, ignoring order and case', () => {
    const fields = buildReviewFields(
      { ...CURRENT, genres: ['shooter', 'Action'] },
      { ...DETAILS, genres: ['Action', 'Shooter'] },
    );
    expect(fields.find((f) => f.key === 'genre')?.same).toBe(true);
  });

  it('leaves a field with nothing fetched unchecked and without a value', () => {
    const fields = buildReviewFields(CURRENT, { ...DETAILS, developer: null, genres: [] });
    const selection = defaultFieldSelection(fields);
    expect(selection.developer).toBe(false);
    expect(selection.genre).toBe(false);
    expect(fields.find((f) => f.key === 'genre')?.value).toBeNull();
  });

  it('reads the release year from the release date', () => {
    const fields = buildReviewFields(CURRENT, DETAILS);
    expect(fields.find((f) => f.key === 'year')?.value).toBe(1993);
  });
});

describe('rating', () => {
  it('normalises provider strings onto the known list', () => {
    expect(normalizeContentRating('M - Mature 17+')).toBe('M');
    expect(normalizeContentRating('E10+ - Everyone 10+')).toBe('E10+');
    expect(normalizeContentRating('pegi 16')).toBe('PEGI 16');
    expect(normalizeContentRating('ESRB: T')).toBeNull();
    expect(normalizeContentRating('Unrated')).toBeNull();
    expect(normalizeContentRating('  ')).toBeNull();
    expect(normalizeContentRating(null)).toBeNull();
  });

  it('starts checked when the game has no rating or the normalised rating matches', () => {
    expect(defaultRatingSelected(null, DETAILS)).toBe(true);
    expect(defaultRatingSelected('M', DETAILS)).toBe(true);
    expect(defaultRatingSelected('T', DETAILS)).toBe(false);
    expect(defaultRatingSelected(null, { ...DETAILS, rating: null })).toBe(false);
  });
});

describe('buildEnrichPayload', () => {
  const fields = buildReviewFields(CURRENT, DETAILS);
  const base = {
    bundleId: 1,
    providerLabel: 'TheGamesDB',
    details: DETAILS,
    fields,
    confirmRatingChange: false,
  };
  const none = {
    fields: {
      title: false,
      year: false,
      description: false,
      genre: false,
      developer: false,
      publisher: false,
    },
    rating: false,
    links: false,
  };

  it('returns null when nothing is checked', () => {
    expect(buildEnrichPayload({ ...base, selection: none })).toBeNull();
  });

  it('sends only checked rows, plus the match identity', () => {
    const payload = buildEnrichPayload({
      ...base,
      selection: { ...none, fields: { ...none.fields, description: true, year: true } },
    });
    expect(payload).toEqual({
      entity_type: 'game_item_bundle',
      entity_id: 1,
      metadata_source: 'TheGamesDB',
      external_game_id: 5,
      description: 'A classic.',
      year: 1993,
    });
  });

  it('omits the rating key unless the rating row is checked', () => {
    const off = buildEnrichPayload({ ...base, selection: { ...none, links: true } });
    expect(off).not.toHaveProperty('content_rating');
    expect(off).not.toHaveProperty('confirm_rating_change');
    const on = buildEnrichPayload({
      ...base,
      selection: { ...none, rating: true },
      confirmRatingChange: true,
    });
    expect(on).toMatchObject({ content_rating: 'M - Mature 17+', confirm_rating_change: true });
  });

  it('sends external_links only when the links row is checked', () => {
    const on = buildEnrichPayload({ ...base, selection: { ...none, links: true } });
    expect(on?.external_links).toEqual(DETAILS.external_links);
    expect(
      buildEnrichPayload({
        ...base,
        selection: { ...none, rating: true },
      }),
    ).not.toHaveProperty('external_links');
  });

  it('counts the checked rows', () => {
    expect(
      countCheckedItems(fields, DETAILS, {
        ...none,
        fields: { ...none.fields, year: true, genre: true },
        rating: true,
        links: true,
      }),
    ).toBe(4);
  });
});

describe('asset selection', () => {
  it('selects everything under the cap, and fills the cap in priority order', () => {
    const assets = [
      ...Array.from({ length: 6 }, (_, i) => asset('screenshot', i + 1)),
      asset('fanart', 1),
      asset('banner', 1),
      asset('clearlogo', 1),
      asset('boxart_back', 1),
      asset('boxart_front', 1),
    ];
    expect(defaultAssetSelection(assets).size).toBe(11);

    const capped = defaultAssetSelection([
      asset('boxart_front', 1),
      ...Array.from({ length: 40 }, (_, i) => asset('screenshot', i + 1)),
      asset('fanart', 1),
    ]);
    expect(capped.size).toBe(ASSET_LIMIT);
    expect(capped.has(asset('boxart_front', 1).url)).toBe(true);
    expect(capped.has(asset('fanart', 1).url)).toBe(true);
    expect(capped.has(asset('screenshot', 3).url)).toBe(true);
    expect(capped.has(asset('screenshot', 40).url)).toBe(false);
  });

  it('defaults the cover to selected front box art, else a cover image, else none', () => {
    const front = asset('boxart_front', 1);
    const cover = asset('cover', 1);
    const shot = asset('screenshot', 1);
    expect(defaultCoverUrl([shot, front, cover], new Set([front.url, cover.url]))).toBe(front.url);
    expect(defaultCoverUrl([shot, front, cover], new Set([cover.url]))).toBe(cover.url);
    expect(defaultCoverUrl([shot, front], new Set([shot.url]))).toBeNull();
  });

  it('drops duplicate urls', () => {
    const a = asset('screenshot', 1);
    expect(uniqueAssets([a, { ...a }, asset('screenshot', 2)])).toHaveLength(2);
  });
});
