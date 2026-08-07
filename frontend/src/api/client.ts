export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  /** The parsed `detail` field from the response body, before stringification —
   *  a plain string in the common case, or a structured object for errors that
   *  need to carry more than a message (e.g. an `error_type` a caller can branch on). */
  readonly rawDetail: unknown;

  constructor(status: number, detail: string, rawDetail?: unknown) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.rawDetail = rawDetail;
    this.name = 'ApiError';
  }
}

export class TimeoutError extends Error {
  constructor() {
    super('Request timed out');
    this.name = 'TimeoutError';
  }
}

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

export function getCsrfToken(): string {
  const pair = document.cookie.split('; ').find((c) => c.startsWith('peach_csrf='));
  return pair ? pair.slice('peach_csrf='.length) : '';
}

const _CSRF_SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);

export interface ApiFetchOptions extends RequestInit {
  /** Overrides the default 10s client-side abort timeout for this call. */
  timeoutMs?: number;
  /**
   * Tracks this request's AbortController under `key` so a later call to
   * `api.abort(key)` (or the `abortRequest` free function) can cancel it
   * without the caller holding a raw controller reference, e.g. a hook that
   * fires a request from one callback and needs to cancel it from another.
   * If a request with the same key is still in flight when a new one starts,
   * the previous one is aborted first (last request for a key wins).
   */
  abortKey?: string;
}

class ApiClient {
  private readonly controllers = new Map<string, AbortController>();

  async fetch<T>(path: string, init: ApiFetchOptions = {}): Promise<T> {
    const { timeoutMs, abortKey, ...requestInit } = init;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Request-ID': crypto.randomUUID(),
      ...(requestInit.headers as Record<string, string> | undefined),
    };

    const method = (requestInit.method ?? 'GET').toUpperCase();
    if (!_CSRF_SAFE.has(method)) {
      headers['X-CSRF-Token'] = getCsrfToken();
    }

    const controller = new AbortController();
    if (abortKey) {
      this.controllers.get(abortKey)?.abort();
      this.controllers.set(abortKey, controller);
    }
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs ?? 10_000);
    const releaseAbortKey = () => {
      if (abortKey && this.controllers.get(abortKey) === controller) {
        this.controllers.delete(abortKey);
      }
    };

    let res: Response;
    try {
      // credentials: "include" is required, it causes the browser to send the
      // HttpOnly peach_token cookie on every cross-origin request to the API.
      res = await fetch(`${baseURL}${path}`, {
        ...requestInit,
        headers,
        credentials: 'include',
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timeoutId);
      releaseAbortKey();
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new TimeoutError();
      }
      throw err;
    }
    clearTimeout(timeoutId);
    releaseAbortKey();

    if (!res.ok) {
      const isSessionError = res.status === 401;

      if (isSessionError) {
        window.dispatchEvent(new CustomEvent('session-expired'));
      }

      let detail = res.statusText;
      let rawDetail: unknown;
      try {
        const body = (await res.json()) as { detail?: unknown };
        const raw = body.detail;
        rawDetail = raw;
        if (typeof raw === 'string') {
          detail = raw;
        } else if (
          raw != null &&
          typeof raw === 'object' &&
          typeof (raw as { message?: unknown }).message === 'string'
        ) {
          // Structured error bodies (e.g. { error_type, message, ... }) still
          // render as plain text here, only rawDetail carries the extra fields.
          detail = (raw as { message: string }).message;
        } else if (raw != null) {
          detail = JSON.stringify(raw);
        }
      } catch {
        // keep statusText as detail
      }

      if (!isSessionError) {
        window.dispatchEvent(new CustomEvent('api-error', { detail }));
      }

      throw new ApiError(res.status, detail, rawDetail);
    }

    if (res.status === 204) return undefined as T;
    const data = await res.json();
    return data as T;
  }

  /** Abort the in-flight request tracked under `key`, if any. No-op if none
   *  is in flight (already finished, or never started under this key). */
  abort(key: string): void {
    this.controllers.get(key)?.abort();
    this.controllers.delete(key);
  }
}

export const api = new ApiClient();

// Re-export as a free function so existing call sites and test mocks continue
// to work without a 50-file rename. All calls delegate to api.fetch.
export const apiFetch = <T>(path: string, init: ApiFetchOptions = {}): Promise<T> =>
  api.fetch<T>(path, init);

export const abortRequest = (key: string): void => api.abort(key);
