import { ApiError } from '@/api/client';

// error_type of the backend's structured 409 (PREVIOUS_ASSETS_ERROR_TYPE in
// backend/service/games/media_link.py): the linked media already holds
// fetched images, so Accept All needs previous_assets set to replace or keep.
export const PREVIOUS_ASSETS_ERROR_TYPE = 'previous_assets_choice_required';

export type PreviousAssetsChoice = 'replace' | 'keep';

/** existing_count from a previous-assets 409, or null for any other error. */
export function previousAssetsCount(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const raw = err.rawDetail as
    { error_type?: unknown; existing_count?: unknown } | null | undefined;
  if (raw == null || typeof raw !== 'object' || raw.error_type !== PREVIOUS_ASSETS_ERROR_TYPE)
    return null;
  return typeof raw.existing_count === 'number' ? raw.existing_count : 0;
}
