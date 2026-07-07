import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, ApiError, TimeoutError } from '@/api/client'
import { useAppContext } from '@/context/useAppContext'
import type { BackgroundJob } from '@/context/_AppContext'

// The import endpoint is a synchronous, unbatched loop over every selected
// item (DB lookups + a shutil.move of the actual media file, which can be a
// slow cross-device copy for large ROM/ISO files, plus a commit per item) —
// there's no background job/status polling for it like there is for the scan
// itself, so the whole batch has to finish inside one HTTP request. Give it
// much more room than apiFetch's 10s default so a handful of large files
// doesn't get mislabeled as a failure while still importing server-side.
const IMPORT_TIMEOUT_MS = 120_000

export interface ScanPreviewItem {
  title: string
  media_path: string
  detected_era: string | null
  is_loose: boolean
  is_zip: boolean
}

// Client-composed view model: the backend's GET /library/scan/status no longer
// carries a preview (scan is stateless — the only copy of a finished scan's
// results lives in its core.jobs result payload), so `preview` here is filled
// in from the job result rather than passed through directly from that endpoint.
export interface ScanStatus {
  running: boolean
  preview: ScanPreviewItem[]
  error: string | null
}

// Raw shape of GET /library/scan/status.
interface ScanStatusResponse {
  running: boolean
  job_id?: string | null
  error: string | null
}

interface ScanJobResult {
  preview?: ScanPreviewItem[]
}

export interface ImportResult {
  imported: number
  skipped: number
  errors: Array<{ path: string; reason: string }>
}

interface UseLibraryScanOptions {
  open: boolean
  onImported: () => void
}

interface ScanTriggerResponse {
  started: boolean
  directory: string
  job_id?: string
  background?: boolean
}

export function useLibraryScan({ open, onImported }: UseLibraryScanOptions) {
  const { dispatch } = useAppContext()
  const [scanning, setScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Monotonic "generation" counter. Every new scan/import operation — and
  // every modal close — bumps this. Any async callback (mutation onSuccess/
  // onError, the status poll, the job-hydration fetch, handleImport's own
  // await) captures the value current at its own start and re-checks it
  // before writing state; if the value has moved on, that callback has been
  // superseded and becomes a no-op instead of clobbering newer state.
  //
  // This matters because the modal's Cancel/Close button is disabled while
  // busy (`disabled={busy}` in ScanModal), but Modal.tsx wraps a native
  // <dialog> with no 'cancel' handler — pressing Escape closes the dialog
  // (and fires onClose -> open=false) regardless of that disabled state,
  // WITHOUT cancelling whatever request is still in flight. Since Library's
  // index.tsx always keeps <ScanModal> mounted (only toggles `open`), this
  // hook instance — and the in-flight promise's closures — stay alive. A
  // user can Escape-close mid-import, reopen, run a second import that
  // succeeds, and then have the first (now-stale) import's catch/then fire
  // afterward and overwrite the freshly-successful UI state. The generation
  // guard makes that stale completion inert.
  const generationRef = useRef(0)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  useEffect(() => {
    if (!open) {
      generationRef.current += 1
      setScanning(false)
      setStatus(null)
      setError(null)
      setImporting(false)
      setImportResult(null)
      if (pollRef.current) clearInterval(pollRef.current)
    } else {
      const generation = generationRef.current
      // Hydrate an already-finished background scan's preview so reopening the
      // modal (e.g. from the Activity bell) shows results without re-scanning.
      // The preview no longer lives behind /scan/status (stateless now) — it's
      // read from the most recent finished scan job's result instead.
      apiFetch<BackgroundJob[]>('/api/v1/jobs')
        .then((allJobs) => {
          if (generationRef.current !== generation) return
          const lastScan = [...allJobs].reverse().find((j) => j.kind === 'scan' && j.status === 'done')
          const preview = (lastScan?.result as ScanJobResult | undefined)?.preview ?? []
          if (preview.length > 0) setStatus({ running: false, preview, error: null })
        })
        .catch(() => {})
    }
  }, [open])

  const scanMutation = useMutation<ScanTriggerResponse, Error>({
    mutationFn: () => apiFetch<ScanTriggerResponse>('/api/v1/library/scan', { method: 'POST' }),
  })

  function handleScan() {
    const generation = ++generationRef.current
    setError(null)
    setStatus(null)
    setImportResult(null)
    setScanning(true)
    scanMutation.mutate(undefined, {
      onSuccess: (resp) => {
        if (generationRef.current !== generation) return
        setScanning(true)
        const jobId = resp?.job_id
        if (jobId) {
          // Surface the scan in the nav-bell Activity panel; for a large
          // (background) scan the user can close this modal and watch it there.
          dispatch({
            type: 'UPSERT_JOB',
            payload: { id: jobId, kind: 'scan', status: 'processing', progress: 0, message: 'Scanning media library…' },
          })
        }
        // Capture this interval's own id locally so its self-check below
        // always clears itself — never a *different* generation's interval
        // that happens to be the one currently referenced by pollRef.
        const intervalId = setInterval(async () => {
          if (generationRef.current !== generation) { clearInterval(intervalId); return }
          try {
            const s = await apiFetch<ScanStatusResponse>('/api/v1/library/scan/status')
            if (generationRef.current !== generation) { clearInterval(intervalId); return }
            if (!s.running) {
              clearInterval(intervalId)
              setScanning(false)
              if (s.error) {
                setStatus({ running: false, preview: [], error: s.error })
              } else if (jobId) {
                // The finished scan's preview lives in the job result, not on
                // this status endpoint (which is now stateless).
                const job = await apiFetch<{ result?: ScanJobResult }>(`/api/v1/jobs/${jobId}`)
                if (generationRef.current !== generation) return
                setStatus({ running: false, preview: job.result?.preview ?? [], error: null })
              } else {
                setStatus({ running: false, preview: [], error: null })
              }
            }
          } catch {
            clearInterval(intervalId)
            if (generationRef.current === generation) setScanning(false)
          }
        }, 1000)
        pollRef.current = intervalId
      },
      onError: (err) => {
        if (generationRef.current !== generation) return
        setError(err instanceof ApiError ? err.detail : 'Scan failed.')
        setScanning(false)
      },
    })
  }

  async function handleImport(selectedPaths: string[]) {
    const generation = ++generationRef.current
    setImporting(true)
    setError(null)
    let result: ImportResult | null = null
    // Backend no longer has a preview cache to read titles/era from — the
    // client submits {path, title, era} per item, sourced from this hook's own
    // (already-fetched) preview list.
    const previewByPath = new Map((status?.preview ?? []).map((p) => [p.media_path, p]))
    const selected = selectedPaths.map((path) => {
      const p = previewByPath.get(path)
      return { path, title: p?.title ?? path, era: p?.detected_era ?? undefined }
    })
    try {
      result = await apiFetch<ImportResult>('/api/v1/library/scan/import', {
        method: 'POST',
        body: JSON.stringify({ selected }),
        timeoutMs: IMPORT_TIMEOUT_MS,
      })
      // A newer scan/import cycle may have started while this request was in
      // flight (e.g. the user Escape-closed the dialog — which bypasses the
      // Cancel button's disabled={busy} guard — then reopened and ran another
      // import). If so, this call is superseded: applying its result now
      // would stomp whatever the newer, current operation already rendered.
      if (generationRef.current === generation) setImportResult(result)
    } catch (err) {
      if (generationRef.current === generation) {
        setError(
          err instanceof ApiError
            ? err.detail
            : err instanceof TimeoutError
              ? 'Import is taking longer than expected — check your library, it may still be processing.'
              : 'Import failed.'
        )
      }
    } finally {
      if (generationRef.current === generation) setImporting(false)
    }
    // Runs outside the fetch's try/catch: onImported() is a cache-invalidation
    // side effect unrelated to the import call itself, and must never be able
    // to retroactively overwrite an already-successful importResult with an
    // unrelated "Import failed" error.
    if (result && result.imported > 0) {
      try {
        onImported()
      } catch (err) {
        console.error('onImported callback failed after a successful import:', err)
      }
    }
  }

  return { scanning, status, error, handleScan, importing, importResult, handleImport }
}
