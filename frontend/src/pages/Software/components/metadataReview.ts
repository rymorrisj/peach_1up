import { RATING_OPTIONS } from '@/generated/constants';
import type { ExternalLink } from './externalLinks';

// Shapes of the metadata routes (backend/api/routes/game_metadata.py). They
// return plain dicts, so the types are declared here by hand.
export interface SearchResult {
  game_id: number;
  title: string;
  release_date: string | null;
  /** Absent in results cached by an older build. */
  platform?: string | null;
}

export interface MetadataAsset {
  url: string;
  type: string;
  thumb_url: string | null;
}

export interface GameDetails {
  game_id: number;
  title: string | null;
  release_date: string | null;
  overview: string | null;
  rating: string | null;
  genres: string[] | null;
  /** Provider genre ids the server could not name; they are not applied. */
  unresolved_genre_ids?: number[];
  developer: string | null;
  publisher: string | null;
  external_links: ExternalLink[];
  assets: MetadataAsset[];
}

/** What the game holds today, compared against the fetched values. */
export interface CurrentMetadata {
  title: string;
  year: number | null;
  description: string | null;
  genres: string[];
  developer: string | null;
  publisher: string | null;
  content_rating: string | null;
}

export type FieldKey = 'title' | 'year' | 'description' | 'genre' | 'developer' | 'publisher';

export interface ReviewField {
  key: FieldKey;
  label: string;
  current: string;
  fetched: string;
  /** What enrich receives for this field, null when nothing was fetched. */
  value: string | number | string[] | null;
  same: boolean;
}

export interface EnrichSelection {
  fields: Record<FieldKey, boolean>;
  rating: boolean;
  links: boolean;
}

function yearOf(releaseDate: string | null): number | null {
  const year = parseInt((releaseDate ?? '').split('-')[0], 10);
  return Number.isNaN(year) ? null : year;
}

function makeField(
  key: FieldKey,
  label: string,
  current: string | number | string[] | null | undefined,
  fetched: string | number | string[] | null | undefined,
): ReviewField {
  const show = (v: string | number | string[] | null | undefined) =>
    Array.isArray(v) ? v.join(', ') : v == null ? '' : String(v);
  const canon = (v: string | number | string[] | null | undefined) =>
    (Array.isArray(v) ? [...v].map((g) => g.toLowerCase()).sort() : [show(v).trim()]).join('|');
  const fetchedText = show(fetched);
  const empty = fetchedText === '' || (Array.isArray(fetched) && fetched.length === 0);
  return {
    key,
    label,
    current: show(current),
    fetched: fetchedText,
    value: empty ? null : (fetched ?? null),
    same: !empty && canon(current) === canon(fetched),
  };
}

export function buildReviewFields(current: CurrentMetadata, details: GameDetails): ReviewField[] {
  return [
    makeField('title', 'Title', current.title, details.title),
    makeField('year', 'Release year', current.year, yearOf(details.release_date)),
    makeField('description', 'Description', current.description, details.overview),
    makeField('genre', 'Genres', current.genres, details.genres),
    makeField('developer', 'Developer', current.developer, details.developer),
    makeField('publisher', 'Publisher', current.publisher, details.publisher),
  ];
}

/** Empty fields (and fields already equal) start checked; a field holding a
 *  different value starts unchecked; a field with nothing fetched is off. */
export function defaultFieldSelection(fields: ReviewField[]): Record<FieldKey, boolean> {
  const selection = {} as Record<FieldKey, boolean>;
  for (const f of fields) selection[f.key] = f.value != null && (f.current === '' || f.same);
  return selection;
}

const RATING_VALUES = new Map(
  RATING_OPTIONS.filter((o) => o.value).map((o) => [o.value.toLowerCase(), o.value]),
);

/** Mirrors normalize_content_rating in backend/core/dependencies.py: the raw
 *  provider string onto the known rating list, or null when unrecognised. The
 *  server stays the authority; this only drives what the preview shows. */
export function normalizeContentRating(raw: string | null | undefined): string | null {
  const text = (raw ?? '').trim();
  if (!text) return null;
  const exact = RATING_VALUES.get(text.toLowerCase());
  if (exact) return exact;
  const lead = text.split(/\s*[-:–]\s*/, 1)[0].trim();
  return RATING_VALUES.get(lead.toLowerCase()) ?? null;
}

export function defaultRatingSelected(current: string | null, details: GameDetails): boolean {
  if (!details.rating?.trim()) return false;
  return !current || normalizeContentRating(details.rating) === current;
}

/** How many metadata rows (fields, rating, links) Apply would send. */
export function countCheckedItems(
  fields: ReviewField[],
  details: GameDetails,
  selection: EnrichSelection,
): number {
  return (
    fields.filter((f) => selection.fields[f.key] && f.value != null).length +
    (selection.rating && details.rating ? 1 : 0) +
    (selection.links && details.external_links.length > 0 ? 1 : 0)
  );
}

/** The enrich body for the checked rows, or null when nothing is checked.
 *  Unchecked rows are left out of the body entirely; the rating key in
 *  particular is omitted, never sent as null. */
export function buildEnrichPayload(args: {
  bundleId: number;
  providerLabel: string;
  details: GameDetails;
  fields: ReviewField[];
  selection: EnrichSelection;
  confirmRatingChange: boolean;
}): Record<string, unknown> | null {
  const { bundleId, providerLabel, details, fields, selection, confirmRatingChange } = args;
  const body: Record<string, unknown> = {};
  for (const f of fields) if (selection.fields[f.key] && f.value != null) body[f.key] = f.value;
  if (selection.rating && details.rating) {
    body.content_rating = details.rating;
    if (confirmRatingChange) body.confirm_rating_change = true;
  }
  if (selection.links && details.external_links.length > 0) {
    body.external_links = details.external_links;
  }
  if (Object.keys(body).length === 0) return null;
  return {
    entity_type: 'game_item_bundle',
    entity_id: bundleId,
    metadata_source: providerLabel,
    external_game_id: details.game_id,
    ...body,
  };
}

// Mirrors ACCEPT_ALL_MAX_ASSETS in backend/service/games/media_link.py, which
// still rejects a larger apply with a 413.
export const ASSET_LIMIT = 30;
const DEFAULT_SCREENSHOTS = 3;

// Display and default-selection priority.
export const ASSET_GROUPS: { type: string; label: string; name: string }[] = [
  { type: 'boxart_front', label: 'Front box art', name: 'Front box art' },
  { type: 'cover', label: 'Cover', name: 'Cover' },
  { type: 'boxart_back', label: 'Back box art', name: 'Back box art' },
  { type: 'clearlogo', label: 'Clear logo', name: 'Clear logo' },
  { type: 'banner', label: 'Banner', name: 'Banner' },
  { type: 'screenshot', label: 'Screenshots', name: 'Screenshot' },
  { type: 'fanart', label: 'Fanart', name: 'Fanart' },
  { type: 'icon', label: 'Icons', name: 'Icon' },
];

export function uniqueAssets(assets: MetadataAsset[]): MetadataAsset[] {
  const seen = new Set<string>();
  return assets.filter((a) => !seen.has(a.url) && seen.add(a.url));
}

export function groupAssets(
  assets: MetadataAsset[],
): { type: string; label: string; name: string; assets: MetadataAsset[] }[] {
  const known = new Set(ASSET_GROUPS.map((g) => g.type));
  const groups = ASSET_GROUPS.map((g) => ({
    ...g,
    assets: assets.filter((a) => a.type === g.type),
  }));
  const other = assets.filter((a) => !known.has(a.type));
  if (other.length > 0)
    groups.push({ type: 'other', label: 'Other', name: 'Image', assets: other });
  return groups.filter((g) => g.assets.length > 0);
}

/** Front box art first, then back box art, clear logo, banner, a few
 *  screenshots, fanart, then whatever is left, capped at ASSET_LIMIT. */
export function defaultAssetSelection(assets: MetadataAsset[]): Set<string> {
  const ofType = (...types: string[]) => assets.filter((a) => types.includes(a.type));
  const screenshots = ofType('screenshot');
  const ordered = [
    ...ofType('boxart_front', 'cover', 'boxart_back', 'clearlogo', 'banner'),
    ...screenshots.slice(0, DEFAULT_SCREENSHOTS),
    ...ofType('fanart'),
    ...screenshots.slice(DEFAULT_SCREENSHOTS),
    ...ofType('icon'),
  ];
  return new Set(ordered.slice(0, ASSET_LIMIT).map((a) => a.url));
}

/** The default cover: a selected front box art image, else a selected cover
 *  image, else null (leave the game cover as it is). */
export function defaultCoverUrl(assets: MetadataAsset[], selected: Set<string>): string | null {
  const chosen = (type: string) => assets.find((a) => a.type === type && selected.has(a.url));
  return (chosen('boxart_front') ?? chosen('cover'))?.url ?? null;
}
