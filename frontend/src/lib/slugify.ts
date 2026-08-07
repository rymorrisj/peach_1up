// Client-side mirror of the canonical slugify() in
// backend/service/utils/slug_generator.py, used only for live "auto-filled
// from name" slug previews in create/edit forms. The backend re-derives and
// persists the authoritative slug on submit; this never writes anything
// itself. Keep this in lockstep with the Python implementation so the
// preview never diverges from what the server will actually save.
export function slugify(name: string, fallback = 'item'): string {
  const hyphenated = name.toLowerCase().replace(/\s+/g, '-');
  const stripped = hyphenated.replace(/[^a-z0-9-]/g, '');
  const trimmed = stripped.replace(/^-+|-+$/g, '');
  return trimmed || fallback;
}
