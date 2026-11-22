import { apiFetch } from '@/api/client';

export interface ConsumeOptions {
  /** Sends confirm_rating_change=true, the retry after a rating-change 409
   *  (see useRatingChangeConfirm). */
  confirmRatingChange?: boolean;
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
    await apiFetch(`${deleteUrl}?confirmation_token=${encodeURIComponent(token)}${confirmParam}`, {
      method: 'DELETE',
    });
  }

  return { issue, consume };
}
