import { getCsrfToken } from '@/api/client';

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

// 8 MB, well under the server's 64 MB per-chunk cap, so the declared manifest
// (chunk counts) always matches the chunks we actually PUT.
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024;

// Route-per-domain (backend/api/routes/uploads.py) replaced the earlier
// single-endpoint-plus-target_type shape: each domain gets its own URL
// (/api/v1/uploads/software-games|software-media|software-apps), its own
// permission check, and no discriminator field travels in the request body
// anymore, the route itself says which domain an upload belongs to. All
// three now have a live backend endpoint. UploadDomain selects the URL only;
// it is never sent over the wire.
export type UploadDomain = 'software_games' | 'software_media' | 'software_apps';

const DOMAIN_PATH: Record<UploadDomain, string> = {
  software_games: 'software-games',
  software_media: 'software-media',
  software_apps: 'software-apps',
};

export interface ChunkedUploadResult {
  /** Always 202, every upload finalizes as a background job now. */
  status: number;
  body: {
    // The finalize result itself (result_type/id/title/disc_count/
    // reused_existing_media for software_games/software_apps, path/slug/
    // size_bytes for software_media) no longer comes back in this response,
    // it lands in the job's own `result` once GET /api/v1/jobs/{job_id}
    // reports it done, since finalize always runs after this call returns.
    // These fields are kept optional here only so callers that still read
    // them (pending their own follow-up update to read from the job
    // instead) don't hit a type error, they will always be undefined.
    result_type?: 'game_item_bundle' | 'app_item_bundle' | 'media_upload';
    id?: number;
    title?: string;
    disc_count?: number;
    reused_existing_media?: boolean;
    path?: string;
    slug?: string;
    size_bytes?: number;
    job_id: string;
    status: string;
  };
}

export interface ChunkedUploadHandle {
  promise: Promise<ChunkedUploadResult>;
  abort: () => void;
}

interface InitResponse {
  upload_id: string;
  chunk_max_bytes: number;
  job_id: string;
}

// Folder uploads preserve their full relative path structure unconditionally,
// not just for a PS3_DISC.SFB folder found exactly one path segment deep.
// That narrow heuristic (N1) missed every other directory-based media shape
// the backend now resolves the same way: an installed_dir PS3 folder with no
// SFB marker (PS3_GAME/USRDIR or bare USRDIR/EBOOT.BIN, which can sit at any
// depth, not just one level in), and an extracted Xbox 360 XEX folder. Trying
// to mirror the backend's shape detection here client-side would mean
// keeping two independent implementations of the same MediaTarget-kind
// classification in sync (exactly the kind of drift the MediaTarget refactor
// exists to close on the backend side) — nesting is comparatively cheap to
// always preserve and let the server's own resolvers (smart_media_detector's
// resolve_ps3_target/resolve_xex_target) sort out the shape, the same way a
// plain flat DOS/console folder upload already reassembles correctly whether
// or not it happens to carry relative_path.
function webkitRelativePathOf(file: File): string | undefined {
  return (file as unknown as { webkitRelativePath?: string }).webkitRelativePath || undefined;
}

// Drops the selected root folder's own name (parts[0]): the server's dest_dir
// already IS that root, re-including it would nest everything one level too
// deep and collide with the slug-named destination directory itself.
function relativePathWithinSelection(file: File): string | undefined {
  const relPath = webkitRelativePathOf(file);
  if (!relPath) return undefined;
  const parts = relPath.split('/');
  return parts.length >= 2 ? parts.slice(1).join('/') : undefined;
}

async function asError(res: Response): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: string };
    return new Error(body.detail ?? `Upload failed (HTTP ${res.status}).`);
  } catch {
    return new Error(`Upload failed (HTTP ${res.status}).`);
  }
}

/**
 * Upload one file (kind "file"), a folder of files (kind "folder"), or an
 * explicitly ordered multi-disc set (kind "set") to the chunked upload
 * endpoints for one domain, reporting 0-100 progress across all chunks.
 * Every upload creates a job on the server at /init (before any bytes have
 * been transferred) and always resolves with status 202 plus that same
 * `job_id`; onJobId, if given, fires as soon as /init returns, so the caller
 * can start tracking the job (e.g. in the nav bell) from the very start of
 * the transfer rather than waiting for /complete. On abort or any error the
 * server-side staging dir is cleaned up via DELETE.
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
  onJobId?: (jobId: string) => void,
  chunkSize: number = DEFAULT_CHUNK_SIZE,
): ChunkedUploadHandle {
  const controller = new AbortController();
  const uploadsBase = `${baseURL}/api/v1/uploads/${DOMAIN_PATH[domain]}`;
  let uploadId: string | null = null;
  let aborted = false;

  const totalBytes = files.reduce((n, f) => n + f.size, 0) || 1;

  const headers = () => ({ 'X-CSRF-Token': getCsrfToken() });

  async function run(): Promise<ChunkedUploadResult> {
    const preserveNesting = kind === 'folder';
    const manifest = files.map((f) => {
      const entry: { name: string; size: number; chunks: number; relative_path?: string } = {
        name: f.name,
        size: f.size,
        chunks: Math.max(1, Math.ceil(f.size / chunkSize)),
      };
      if (preserveNesting) {
        const relativePath = relativePathWithinSelection(f);
        if (relativePath) entry.relative_path = relativePath;
      }
      return entry;
    });

    const initRes = await fetch(`${uploadsBase}/init`, {
      method: 'POST',
      credentials: 'include',
      headers: { ...headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, title, files: manifest }),
      signal: controller.signal,
    });
    if (!initRes.ok) throw await asError(initRes);
    const init = (await initRes.json()) as InitResponse;
    uploadId = init.upload_id;
    onJobId?.(init.job_id);

    let uploaded = 0;
    for (let fi = 0; fi < files.length; fi++) {
      const file = files[fi];
      const chunks = Math.max(1, Math.ceil(file.size / chunkSize));
      for (let ci = 0; ci < chunks; ci++) {
        if (aborted) throw new Error('Upload cancelled.');
        const start = ci * chunkSize;
        const blob = file.slice(start, Math.min(start + chunkSize, file.size));
        const fd = new FormData();
        fd.append('chunk', blob, `${ci}.part`);
        const res = await fetch(`${uploadsBase}/${uploadId}/chunks/${fi}/${ci}`, {
          method: 'PUT',
          credentials: 'include',
          headers: headers(),
          body: fd,
          signal: controller.signal,
        });
        if (!res.ok) throw await asError(res);
        uploaded += blob.size;
        onProgress(Math.round((uploaded / totalBytes) * 100));
      }
    }

    const completeRes = await fetch(`${uploadsBase}/${uploadId}/complete`, {
      method: 'POST',
      credentials: 'include',
      headers: headers(),
      signal: controller.signal,
    });
    if (!completeRes.ok) throw await asError(completeRes);
    const body = (await completeRes.json().catch(() => ({}))) as ChunkedUploadResult['body'];
    // A 202 with no job_id means the response body failed to parse (or the
    // server sent an unexpected shape) — silently returning body={} here would
    // strand the background job with no id to poll/track, and look identical
    // to a successful inline finalize to the caller. Treat it as a hard error
    // instead of a quiet success.
    if (completeRes.status === 202 && !body.job_id) {
      throw new Error(
        'Upload was accepted for background processing, but the server response could not be read.',
      );
    }
    onProgress(100);
    return { status: completeRes.status, body };
  }

  const promise = run().catch(async (err: unknown) => {
    if (uploadId) {
      // Best-effort staging cleanup; ignore failures (orphan sweeper backstops).
      try {
        await fetch(`${uploadsBase}/${uploadId}`, {
          method: 'DELETE',
          credentials: 'include',
          headers: headers(),
        });
      } catch {
        /* ignore */
      }
    }
    throw err instanceof Error ? err : new Error('Upload failed.');
  });

  return {
    promise,
    abort: () => {
      aborted = true;
      controller.abort();
    },
  };
}
