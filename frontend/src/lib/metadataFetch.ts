// Shared copy and pure rules for the owner's metadata_fetch_enabled setting.
// The backend refuses every metadata route while it is off (see
// backend/api/routes/game_metadata.py), these only drive what the UI shows.

// Settings modal body and hover hint for the "Enable metadata fetching" toggle.
export const METADATA_FETCH_DISCLAIMER =
  'Fetched metadata can be wrong. Review and confirm what is retrieved before you keep it, especially titles, ratings and cover art. Ratings affect what restricted accounts can see.';

// Tooltip on Fetch Metadata and Cover Art while the setting is off.
export const METADATA_FETCH_DISABLED_HINT = 'Enable metadata fetching in Settings';

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
