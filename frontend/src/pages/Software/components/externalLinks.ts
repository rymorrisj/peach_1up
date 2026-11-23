// A provider or trailer link on a game, as the read model carries it
// (backend/service/metadata_providers/links.py). Only plain http(s) URLs are
// ever rendered; the page never embeds, fetches or follows them.
export interface ExternalLink {
  type: string;
  url: string;
  source?: string;
}

export const LINK_GROUPS: { type: string; label: string }[] = [
  { type: 'trailer', label: 'Trailers' },
  { type: 'official', label: 'Official sites' },
  { type: 'store', label: 'Stores' },
  { type: 'wiki', label: 'Wikis' },
  { type: 'social', label: 'Social' },
  { type: 'other', label: 'Other' },
];

export function isWebUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  try {
    const { protocol } = new URL(value);
    return protocol === 'http:' || protocol === 'https:';
  } catch {
    return false;
  }
}

/** Only the entries with an http(s) URL, in their original order. */
export function webLinks(links: readonly unknown[] | null | undefined): ExternalLink[] {
  const out: ExternalLink[] = [];
  for (const entry of links ?? []) {
    if (entry == null || typeof entry !== 'object') continue;
    const { type, url, source } = entry as Partial<ExternalLink>;
    if (!isWebUrl(url)) continue;
    out.push({ type: typeof type === 'string' ? type : 'other', url, source });
  }
  return out;
}

/** Links bucketed under LINK_GROUPS; an unknown type lands in "other". */
export function groupLinks(links: ExternalLink[]): { label: string; links: ExternalLink[] }[] {
  const known = new Set(LINK_GROUPS.map((g) => g.type));
  return LINK_GROUPS.map((group) => ({
    label: group.label,
    links: links.filter((l) => (known.has(l.type) ? l.type : 'other') === group.type),
  })).filter((group) => group.links.length > 0);
}
