import { getCsrfToken } from '@/api/client'

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

// 8 MB, well under the server's 64 MB per-chunk cap, so the declared manifest
// (chunk counts) always matches the chunks we actually PUT.
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024

// PROVISIONAL CONTRACT (subject to change once the backend discovery session
// locks the real contract). Today only "game_item_bundle" is backed by a real
// endpoint (/api/v1/game-items/uploads/*, games-only). "media_item_bundle" and
// "app_item" are forward-built against the documented-but-unconfirmed shared
// upload endpoint and have no live backend counterpart yet.
export type UploadTargetType = 'game_item_bundle' | 'media_item_bundle' | 'app_item'

export interface ChunkedUploadResult {
  /** 201 when finalized inline, 202 when a background job was created. */
  status: number
  body: {
    target_type?: UploadTargetType
    title?: string
    disc_count?: number
    reused_existing_media?: boolean
    job_id?: string
    status?: string
  }
}

export interface ChunkedUploadHandle {
  promise: Promise<ChunkedUploadResult>
  abort: () => void
}

interface InitResponse {
  upload_id: string
  chunk_max_bytes: number
}

async function asError(res: Response): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: string }
    return new Error(body.detail ?? `Upload failed (HTTP ${res.status}).`)
  } catch {
    return new Error(`Upload failed (HTTP ${res.status}).`)
  }
}

// PROVISIONAL CONTRACT: a single domain-agnostic upload endpoint
// (/api/v1/uploads/*) with target_type carried in the init body/URL instead of
// a route segment (e.g. the old games-only /api/v1/game-items/uploads/*).
// Chunk assembly and the begin/stream/finalize step shape are otherwise
// unchanged from the pre-existing game-items flow. Adjust this base path (and
// the init body shape) once the backend discovery session confirms the real
// contract.
const UPLOADS_BASE = `${baseURL}/api/v1/uploads`

/**
 * Upload one file (kind "file"), a folder of files (kind "folder"), or an
 * explicitly ordered multi-disc set (kind "set") to the chunked upload
 * endpoints, reporting 0-100 progress across all chunks. Small uploads
 * resolve with status 201 and the created item/set; uploads over the
 * server's background threshold resolve with 202 and a `job_id` to track in
 * the nav bell. On abort or any error the server-side staging dir is cleaned
 * up via DELETE.
 *
 * `targetType` selects which domain the finished upload is ingested into
 * (game_item_bundle, media_item_bundle, app_item), see the PROVISIONAL
 * CONTRACT note above.
 */
export function chunkedUpload(
  kind: 'file' | 'folder' | 'set',
  title: string,
  files: File[],
  onProgress: (pct: number) => void,
  targetType: UploadTargetType,
  chunkSize: number = DEFAULT_CHUNK_SIZE,
): ChunkedUploadHandle {
  const controller = new AbortController()
  let uploadId: string | null = null
  let aborted = false

  const totalBytes = files.reduce((n, f) => n + f.size, 0) || 1

  const headers = () => ({ 'X-CSRF-Token': getCsrfToken() })

  async function run(): Promise<ChunkedUploadResult> {
    const manifest = files.map((f) => ({
      name: f.name,
      size: f.size,
      chunks: Math.max(1, Math.ceil(f.size / chunkSize)),
    }))

    const initRes = await fetch(`${UPLOADS_BASE}/init`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers(), 'Content-Type': 'application/json' },
      // target_type replaces the old route-based domain (game-items/uploads).
      body: JSON.stringify({ kind, title, files: manifest, target_type: targetType }),
      signal: controller.signal,
    })
    if (!initRes.ok) throw await asError(initRes)
    const init = (await initRes.json()) as InitResponse
    uploadId = init.upload_id

    let uploaded = 0
    for (let fi = 0; fi < files.length; fi++) {
      const file = files[fi]
      const chunks = Math.max(1, Math.ceil(file.size / chunkSize))
      for (let ci = 0; ci < chunks; ci++) {
        if (aborted) throw new Error('Upload cancelled.')
        const start = ci * chunkSize
        const blob = file.slice(start, Math.min(start + chunkSize, file.size))
        const fd = new FormData()
        fd.append('chunk', blob, `${ci}.part`)
        const res = await fetch(
          `${UPLOADS_BASE}/${uploadId}/chunks/${fi}/${ci}`,
          { method: 'PUT', credentials: 'include', headers: headers(), body: fd, signal: controller.signal },
        )
        if (!res.ok) throw await asError(res)
        uploaded += blob.size
        onProgress(Math.round((uploaded / totalBytes) * 100))
      }
    }

    const completeRes = await fetch(`${UPLOADS_BASE}/${uploadId}/complete`, {
      method: 'POST',
      credentials: 'include',
      headers: headers(),
      signal: controller.signal,
    })
    if (!completeRes.ok) throw await asError(completeRes)
    const body = (await completeRes.json().catch(() => ({}))) as ChunkedUploadResult['body']
    onProgress(100)
    return { status: completeRes.status, body }
  }

  const promise = run().catch(async (err: unknown) => {
    if (uploadId) {
      // Best-effort staging cleanup; ignore failures (orphan sweeper backstops).
      try {
        await fetch(`${UPLOADS_BASE}/${uploadId}`, {
          method: 'DELETE',
          credentials: 'include',
          headers: headers(),
        })
      } catch {
        /* ignore */
      }
    }
    throw err instanceof Error ? err : new Error('Upload failed.')
  })

  return {
    promise,
    abort: () => {
      aborted = true
      controller.abort()
    },
  }
}
