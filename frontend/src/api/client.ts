export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.name = "ApiError";
  }
}

export class TimeoutError extends Error {
  constructor() {
    super("Request timed out");
    this.name = "TimeoutError";
  }
}

const baseURL =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  "http://localhost:8000";

export function getCsrfToken(): string {
  const pair = document.cookie.split('; ').find(c => c.startsWith('peach_csrf='));
  return pair ? pair.slice('peach_csrf='.length) : '';
}

const _CSRF_SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);

export interface ApiFetchOptions extends RequestInit {
  /** Overrides the default 10s client-side abort timeout for this call. */
  timeoutMs?: number;
}

class ApiClient {
  async fetch<T>(path: string, init: ApiFetchOptions = {}): Promise<T> {
    const { timeoutMs, ...requestInit } = init;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Request-ID": crypto.randomUUID(),
      ...(requestInit.headers as Record<string, string> | undefined),
    };

    const method = (requestInit.method ?? 'GET').toUpperCase();
    if (!_CSRF_SAFE.has(method)) {
      headers['X-CSRF-Token'] = getCsrfToken();
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs ?? 10_000);

    let res: Response;
    try {
      // credentials: "include" is required — it causes the browser to send the
      // HttpOnly peach_token cookie on every cross-origin request to the API.
      res = await fetch(`${baseURL}${path}`, {
        ...requestInit,
        headers,
        credentials: "include",
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timeoutId);
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new TimeoutError();
      }
      throw err;
    }
    clearTimeout(timeoutId);

    if (!res.ok) {
      const isSessionError = res.status === 401;

      if (isSessionError) {
        window.dispatchEvent(new CustomEvent("session-expired"));
      }

      let detail = res.statusText;
      try {
        const body = (await res.json()) as { detail?: unknown };
        const raw = body.detail;
        detail =
          typeof raw === "string"
            ? raw
            : raw != null
              ? JSON.stringify(raw)
              : detail;
      } catch {
        // keep statusText as detail
      }

      if (!isSessionError) {
        window.dispatchEvent(new CustomEvent("api-error", { detail }));
      }

      throw new ApiError(res.status, detail);
    }

    if (res.status === 204) return undefined as T;
    const data = await res.json();
    return data as T;
  }
}

export const api = new ApiClient();

// Re-export as a free function so existing call sites and test mocks continue
// to work without a 50-file rename. All calls delegate to api.fetch.
export const apiFetch = <T>(path: string, init: ApiFetchOptions = {}): Promise<T> =>
  api.fetch<T>(path, init);
