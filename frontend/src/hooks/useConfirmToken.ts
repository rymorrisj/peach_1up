import { apiFetch } from '@/api/client';
import { RATING_CHANGE_ERROR_TYPE } from './useRatingChangeConfirm';

export interface ConsumeOptions {
  /** Sends confirm_rating_change=true, the retry after a rating-change 409
   *  (see useRatingChangeConfirm). */
  confirmRatingChange?: boolean;
  /** Sends delete_media=true|false: the delete-confirm checkbox's choice for
   *  this delete only. It rides on the confirmed DELETE itself, so nothing is
   *  persisted if the user cancels a later prompt. Omitted, the bundle's own
   *  delete_media_override (else the global setting) applies. */
  deleteMedia?: boolean;
  /** The caller wraps this consume in useRatingChangeConfirm, which shows its
   *  own dialog for the rating-change 409, so the generic error toast is
   *  suppressed for that one error. Every other error still toasts. */
  ratingChangeHandled?: boolean;
}

export function useConfirmToken() {
  async function issue(confirmUrl: string): Promise<string> {
    const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(confirmUrl, {
      method: 'POST',
    });
    return confirmation_token;
  }

  async function consume(deleteUrl: string, token: string, options: ConsumeOptions = {}): Promise<void> {
    const confirmParam = options.confirmRatingChange ? '&confirm_rating_change=true' : '';
    const deleteMediaParam =
      options.deleteMedia === undefined ? '' : `&delete_media=${options.deleteMedia ? 'true' : 'false'}`;
    await apiFetch(
      `${deleteUrl}?confirmation_token=${encodeURIComponent(token)}${confirmParam}${deleteMediaParam}`,
      {
        method: 'DELETE',
        ...(options.ratingChangeHandled ? { quietErrorTypes: [RATING_CHANGE_ERROR_TYPE] } : {}),
      },
    );
  }

  return { issue, consume };
}
