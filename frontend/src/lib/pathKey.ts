// Comparison key for two filesystem paths: separators unified, "." and ".."
// folded, repeated and trailing separators dropped, case folded (Windows
// only). Counterpart of lexical_key in backend/service/media/file_cleanup.py.
// Never touches the filesystem, so it cannot see through junctions or short
// names; the backend stays the authority for anything beyond display.
export function pathKey(raw: string): string {
  const segments: string[] = [];
  for (const segment of raw.replace(/\\/g, '/').split('/')) {
    if (segment === '' || segment === '.') continue;
    if (segment === '..') segments.pop();
    else segments.push(segment);
  }
  return segments.join('/').toLowerCase();
}
