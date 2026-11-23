// Shared copy and pure rules for the owner's metadata_fetch_enabled setting.
// The backend refuses every metadata route while it is off (see
// backend/api/routes/game_metadata.py), these only drive what the UI shows.

// Settings modal body and hover hint for the "Enable metadata fetching" toggle.
export const METADATA_FETCH_DISCLAIMER =
  'Fetched metadata can be wrong. Review and confirm what is retrieved before you keep it, especially titles, ratings and cover art. Ratings affect what restricted accounts can see.';

// Tooltip on Fetch Metadata while the setting is off.
export const METADATA_FETCH_DISABLED_HINT = 'Enable metadata fetching in Settings';

// Search and details wait on the provider, whose worst case the server bounds
// at 90 seconds (it answers 502 or 504 with a message before that), so the
// client must not give up first at apiFetch's 10 second default.
export const METADATA_LOOKUP_TIMEOUT_MS = 90_000;

// Text for a failed search or details call. The server's 502 and 504 messages
// name the provider and the cause, so they are shown as they are; only a
// client-side abort has no server message and gets its own wording.
export function lookupErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.name === 'TimeoutError') {
    return 'The provider did not answer within 90 seconds. Try again.';
  }
  return err instanceof Error && err.message ? err.message : fallback;
}

// Fails closed: anything other than a stored `true` (including settings not
// loaded yet) reads as off.
export function isMetadataFetchEnabled(settings: Record<string, unknown> | undefined): boolean {
  return settings?.metadata_fetch_enabled === true;
}

// Tooltip for a metadata action button. The off state takes precedence over
// the missing-credentials message; `enabledTitle` is used when neither applies.
export function metadataActionTitle(
  fetchEnabled: boolean,
  providerEnabled: boolean,
  credentialsTitle: string,
  enabledTitle?: string,
): string | undefined {
  if (!fetchEnabled) return METADATA_FETCH_DISABLED_HINT;
  if (!providerEnabled) return credentialsTitle;
  return enabledTitle;
}
