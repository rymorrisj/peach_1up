import { getCsrfToken } from '@/api/client'

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

// 8 MB — well under the server's 64 MB per-chunk cap, so the declared manifest
// (chunk counts) always matches the chunks we actually PUT.
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024

export interface ChunkedUploadResult {
  /** 201 when finalized inline, 202 when a background job was created. */
  status: number
  body: {
    result_type?: 'library_collection'
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

/**
 * Upload one file (kind "file") or a folder of files (kind "folder") to the
 * chunked upload endpoints, reporting 0–100 progress across all chunks. Small
 * uploads resolve with status 201 and the created item/set; uploads over the
 * server's background threshold resolve with 202 and a `job_id` to track in the
 * nav bell. On abort or any error the server-side staging dir is cleaned up via
 * DELETE.
 */
export function chunkedUpload(
  kind: 'file' | 'folder',
  title: string,
  files: File[],
  onProgress: (pct: number) => void,
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

    const initRes = await fetch(`${baseURL}/api/v1/library/uploads/init`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, title, files: manifest }),
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
          `${baseURL}/api/v1/library/uploads/${uploadId}/chunks/${fi}/${ci}`,
          { method: 'PUT', credentials: 'include', headers: headers(), body: fd, signal: controller.signal },
        )
        if (!res.ok) throw await asError(res)
        uploaded += blob.size
        onProgress(Math.round((uploaded / totalBytes) * 100))
      }
    }

    const completeRes = await fetch(`${baseURL}/api/v1/library/uploads/${uploadId}/complete`, {
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
        await fetch(`${baseURL}/api/v1/library/uploads/${uploadId}`, {
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
