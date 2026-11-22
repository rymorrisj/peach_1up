import { useCallback } from 'react';
import { ApiError } from '@/api/client';
import type { ConfirmOptions } from './useConfirm';

// error_type of the backend's structured 409 (RATING_CHANGE_ERROR_TYPE in
// backend/service/media/rating_change_guard.py), raised when an action would
// loosen the effective content rating of linked media.
export const RATING_CHANGE_ERROR_TYPE = 'rating_change_requires_confirmation';

/** affected_count from a rating-change 409, or null for any other error. */
export function ratingChangeAffectedCount(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const raw = err.rawDetail as { error_type?: unknown; affected_count?: unknown } | null | undefined;
  if (raw == null || typeof raw !== 'object' || raw.error_type !== RATING_CHANGE_ERROR_TYPE) return null;
  return typeof raw.affected_count === 'number' ? raw.affected_count : 0;
}

export function ratingChangeMessage(count: number): string {
  return `This changes who can see ${count} media ${count === 1 ? 'item' : 'items'}. Continue?`;
}

/**
 * Wraps an action the backend may refuse with a rating-change 409 (entity
 * link create or remove, game delete, media item move). On that 409 it asks
 * once through the caller's own useConfirm dialog and, if confirmed, runs the
 * action again with confirmRatingChange=true. Any other error, and any error
 * from the retry, propagates to the caller. Resolves true when the action
 * completed, false when the user cancelled the prompt.
 */
export function useRatingChangeConfirm(confirm: (options: ConfirmOptions) => Promise<boolean>) {
  return useCallback(
    async (run: (confirmRatingChange: boolean) => Promise<void>): Promise<boolean> => {
      try {
        await run(false);
        return true;
      } catch (err) {
        const count = ratingChangeAffectedCount(err);
        if (count === null) throw err;
        const confirmed = await confirm({
          title: 'Change who can see media?',
          consequence: ratingChangeMessage(count),
          destructive: true,
        });
        if (!confirmed) return false;
        await run(true);
        return true;
      }
    },
    [confirm],
  );
}
