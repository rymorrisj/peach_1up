import { getCsrfToken } from '@/api/client'

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

// 8 MB, well under the server's 64 MB per-chunk cap, so the declared manifest
// (chunk counts) always matches the chunks we actually PUT.
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024

// Route-per-domain (backend/api/routes/uploads.py) replaced the earlier
// single-endpoint-plus-target_type shape: each domain gets its own URL
// (/api/v1/uploads/software-games|software-media|software-apps), its own
// permission check, and no discriminator field travels in the request body
// anymore, the route itself says which domain an upload belongs to. All
// three now have a live backend endpoint. UploadDomain selects the URL only;
// it is never sent over the wire.
export type UploadDomain = 'software_games' | 'software_media' | 'software_apps'

const DOMAIN_PATH: Record<UploadDomain, string> = {
  software_games: 'software-games',
  software_media: 'software-media',
  software_apps: 'software-apps',
}

export interface ChunkedUploadResult {
  /** 201 when finalized inline, 202 when a background job was created. */
  status: number
  body: {
    // Present for software_games/software_apps, whose finalize creates the
    // DB row directly.
    result_type?: 'game_item_bundle' | 'app_item_bundle' | 'media_upload'
    id?: number
    title?: string
    disc_count?: number
    reused_existing_media?: boolean
    // Present for software_media only, that domain's finalize stages bytes
    // and returns the staged path/slug instead of creating a row (see
    // backend/service/uploads/software_media.py). The caller is responsible
    // for a follow-up POST /api/v1/media-items with this path.
    path?: string
    slug?: string
    size_bytes?: number
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

// PS3 disc dumps (PS3_GAME/, PS3_DISC.SFB, optionally PS3_UPDATE/) are the one
// upload shape where nested folder structure must survive the transport,
// RPCS3 walks EBOOT.BIN from inside PS3_GAME/USRDIR/ itself, and the backend
// already treats a PS3_DISC.SFB-marked folder as its own launch unit (see
// backend/service/backends/rpcs3.py). Every other upload keeps flattening to
// a bare basename unchanged; only this detection opts a "folder" upload into
// sending relative_path at all.
function webkitRelativePathOf(file: File): string | undefined {
  return (file as unknown as { webkitRelativePath?: string }).webkitRelativePath || undefined
}

function isDiscFormatFolderUpload(files: File[]): boolean {
  return files.some((f) => {
    const relPath = webkitRelativePathOf(f)
    if (!relPath) return false
    const parts = relPath.split('/')
    return parts.length === 2 && parts[1].toUpperCase() === 'PS3_DISC.SFB'
  })
}

// Drops the selected root folder's own name (parts[0]): the server's dest_dir
// already IS that root, re-including it would nest everything one level too
// deep and collide with the slug-named destination directory itself.
function relativePathWithinSelection(file: File): string | undefined {
  const relPath = webkitRelativePathOf(file)
  if (!relPath) return undefined
  const parts = relPath.split('/')
  return parts.length >= 2 ? parts.slice(1).join('/') : undefined
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
 * Upload one file (kind "file"), a folder of files (kind "folder"), or an
 * explicitly ordered multi-disc set (kind "set") to the chunked upload
 * endpoints for one domain, reporting 0-100 progress across all chunks.
 * Small uploads resolve with status 201; uploads over the server's
 * background threshold resolve with 202 and a `job_id` to track in the nav
 * bell. On abort or any error the server-side staging dir is cleaned up via
 * DELETE.
 *
 * Not every domain accepts every kind, software_media accepts "file" only,
 * software_apps accepts "file"/"folder" (no "set"), software_games accepts
 * all three. The server enforces this (422 on an unsupported kind); this
 * function does not duplicate that check.
 */
export function chunkedUpload(
  kind: 'file' | 'folder' | 'set',
  title: string,
  files: File[],
  onProgress: (pct: number) => void,
  domain: UploadDomain,
  chunkSize: number = DEFAULT_CHUNK_SIZE,
): ChunkedUploadHandle {
  const controller = new AbortController()
  const uploadsBase = `${baseURL}/api/v1/uploads/${DOMAIN_PATH[domain]}`
  let uploadId: string | null = null
  let aborted = false

  const totalBytes = files.reduce((n, f) => n + f.size, 0) || 1

  const headers = () => ({ 'X-CSRF-Token': getCsrfToken() })

  async function run(): Promise<ChunkedUploadResult> {
    const discFormat = kind === 'folder' && isDiscFormatFolderUpload(files)
    const manifest = files.map((f) => {
      const entry: { name: string; size: number; chunks: number; relative_path?: string } = {
        name: f.name,
        size: f.size,
        chunks: Math.max(1, Math.ceil(f.size / chunkSize)),
      }
      if (discFormat) {
        const relativePath = relativePathWithinSelection(f)
        if (relativePath) entry.relative_path = relativePath
      }
      return entry
    })

    const initRes = await fetch(`${uploadsBase}/init`, {
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
          `${uploadsBase}/${uploadId}/chunks/${fi}/${ci}`,
          { method: 'PUT', credentials: 'include', headers: headers(), body: fd, signal: controller.signal },
        )
        if (!res.ok) throw await asError(res)
        uploaded += blob.size
        onProgress(Math.round((uploaded / totalBytes) * 100))
      }
    }

    const completeRes = await fetch(`${uploadsBase}/${uploadId}/complete`, {
      method: 'POST',
      credentials: 'include',
      headers: headers(),
      signal: controller.signal,
    })
    if (!completeRes.ok) throw await asError(completeRes)
    const body = (await completeRes.json().catch(() => ({}))) as ChunkedUploadResult['body']
    // A 202 with no job_id means the response body failed to parse (or the
    // server sent an unexpected shape) — silently returning body={} here would
    // strand the background job with no id to poll/track, and look identical
    // to a successful inline finalize to the caller. Treat it as a hard error
    // instead of a quiet success.
    if (completeRes.status === 202 && !body.job_id) {
      throw new Error('Upload was accepted for background processing, but the server response could not be read.')
    }
    onProgress(100)
    return { status: completeRes.status, body }
  }

  const promise = run().catch(async (err: unknown) => {
    if (uploadId) {
      // Best-effort staging cleanup; ignore failures (orphan sweeper backstops).
      try {
        await fetch(`${uploadsBase}/${uploadId}`, {
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
