// Backend timestamps (SQLite DateTime columns, e.g. LaunchHistory.started_at,
// GameItemBundle.metadata_fetched_at) are naive UTC, serialized with no
// timezone suffix. `new Date(str)` on a suffix-less ISO string is parsed as
// local time by JS, silently shifting every timestamp by the viewer's UTC
// offset. Appending 'Z' before parsing is the fix; centralized here so every
// call site treats these values the same way instead of some appending 'Z'
// and others not (the offset drift this previously caused).
export function parseNaiveUtc(value: string): Date {
  return new Date(value.endsWith('Z') ? value : `${value}Z`);
}
