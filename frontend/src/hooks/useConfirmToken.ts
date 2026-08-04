import { apiFetch } from '@/api/client';

export function useConfirmToken() {
  async function issue(confirmUrl: string): Promise<string> {
    const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(confirmUrl, {
      method: 'POST',
    });
    return confirmation_token;
  }

  async function consume(deleteUrl: string, token: string): Promise<void> {
    await apiFetch(`${deleteUrl}?confirmation_token=${encodeURIComponent(token)}`, {
      method: 'DELETE',
    });
  }

  return { issue, consume };
}
