export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
    this.name = 'ApiError'
  }
}

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

let _sessionToken: string | null = null

export function setSessionToken(token: string | null) {
  _sessionToken = token
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-ID': crypto.randomUUID(),
    ...(init.headers as Record<string, string> | undefined),
  }

  if (_sessionToken) {
    headers['Authorization'] = `Bearer ${_sessionToken}`
  }

  const res = await fetch(`${baseURL}${path}`, { ...init, headers, credentials: 'include' })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      const raw = body.detail
      detail = typeof raw === 'string' ? raw : raw != null ? JSON.stringify(raw) : detail
    } catch {
      // keep statusText as detail
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
