import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, abortRequest, ApiError, TimeoutError } from '@/api/client'
import { useAppContext } from '@/context/useAppContext'
import type { BackgroundJob } from '@/context/_AppContext'

// Centralized-abort key for the scan status poll, scoped per job so a stale
// poll tick from a previous scan can never be mistaken for the current one's.
const scanStatusAbortKey = (jobId: string) => `library-scan-status:${jobId}`

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
  file_path: string
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
  /** True when this status reflects a user-cancelled scan rather than a
   *  normal completion or a real error. */
  cancelled?: boolean
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

// Shape of GET /api/v1/jobs/{id} that this hook actually reads — status (to
// distinguish a cancelled finish from a normal one) plus the preview result.
type ScanJobFetch = Pick<BackgroundJob, 'status'> & { result?: ScanJobResult }

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
  const [cancelling, setCancelling] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Current scan's job id, so handleCancelScan (fired from a separate click,
  // not from inside the mutation's own onSuccess closure) knows what to cancel.
  const jobIdRef = useRef<string | null>(null)

  // Monotonic "generation" counter. Every new scan/import operation — and
  // every modal close — bumps this. Any async callback (mutation onSuccess/
  // onError, the status poll, the job-hydration fetch, handleImport's own
  // await) captures the value current at its own start and re-checks it
  // before writing state; if the value has moved on, that callback has been
  // superseded and becomes a no-op instead of clobbering newer state.
  //
  // This matters because Library's index.tsx always keeps <ScanModal> mounted
  // (only toggles `open`), so this hook instance — and any in-flight promise's
  // closures — stay alive across opens/closes. Modal.tsx blocks Escape while
  // busy, and the Cancel button is disabled during import, but scanning can
  // now be dismissed early (the scan continues as a tracked background job).
  // A user can dismiss mid-scan, reopen, run a second scan/import that
  // succeeds, and then have the first (now-stale) operation's catch/then fire
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
      setCancelling(false)
      if (pollRef.current) clearInterval(pollRef.current)
      if (jobIdRef.current) abortRequest(scanStatusAbortKey(jobIdRef.current))
      jobIdRef.current = null
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
    mutationFn: () => apiFetch<ScanTriggerResponse>('/api/v1/software/scan', { method: 'POST' }),
  })

  // Shared by the post-trigger poll (handleScan) and the post-cancel poll
  // (handleCancelScan) — both just want to know when `running` flips to false
  // and then resolve the job's final status/preview. Each tick's request is
  // tagged with this job's abortKey so handleCancelScan can cut off a tick
  // that's already in flight instead of waiting for it to resolve on its own.
  function startStatusPoll(jobId: string | undefined, generation: number) {
    const intervalId = setInterval(async () => {
      if (generationRef.current !== generation) { clearInterval(intervalId); return }
      try {
        const s = await apiFetch<ScanStatusResponse>('/api/v1/software/scan/status', {
          ...(jobId ? { abortKey: scanStatusAbortKey(jobId) } : {}),
        })
        if (generationRef.current !== generation) { clearInterval(intervalId); return }
        if (!s.running) {
          clearInterval(intervalId)
          setScanning(false)
          if (jobId) {
            // The finished scan's status/preview live on the job, not on this
            // status endpoint (which is now stateless) — status alone isn't
            // enough to tell a cancelled finish from a normal one.
            const job = await apiFetch<ScanJobFetch>(`/api/v1/jobs/${jobId}`)
            if (generationRef.current !== generation) return
            if (job.status === 'cancelled') {
              setStatus({ running: false, preview: [], error: null, cancelled: true })
            } else if (s.error) {
              setStatus({ running: false, preview: [], error: s.error })
            } else {
              setStatus({ running: false, preview: job.result?.preview ?? [], error: null })
            }
          } else if (s.error) {
            setStatus({ running: false, preview: [], error: s.error })
          } else {
            setStatus({ running: false, preview: [], error: null })
          }
        }
      } catch (err) {
        // A deliberate abort (handleCancelScan cutting off this tick) throws
        // TimeoutError same as a real timeout — either way this tick is dead,
        // but only handleCancelScan's own poll restart should decide what
        // happens next, not this stale tick's catch block.
        if (err instanceof TimeoutError && generationRef.current === generation && pollRef.current !== intervalId) {
          return
        }
        clearInterval(intervalId)
        if (generationRef.current === generation) setScanning(false)
      }
    }, 1000)
    pollRef.current = intervalId
    return intervalId
  }

  function handleScan() {
    const generation = ++generationRef.current
    setError(null)
    setStatus(null)
    setImportResult(null)
    setScanning(true)
    jobIdRef.current = null
    scanMutation.mutate(undefined, {
      onSuccess: (resp) => {
        if (generationRef.current !== generation) return
        setScanning(true)
        const jobId = resp?.job_id
        jobIdRef.current = jobId ?? null
        if (jobId) {
          // Surface the scan in the nav-bell Activity panel; for a large
          // (background) scan the user can close this modal and watch it there.
          dispatch({
            type: 'UPSERT_JOB',
            payload: { id: jobId, kind: 'scan', status: 'processing', progress: 0, message: 'Scanning media library…' },
          })
        }
        startStatusPoll(jobId, generation)
      },
      onError: (err) => {
        if (generationRef.current !== generation) return
        setError(err instanceof ApiError ? err.detail : 'Scan failed.')
        setScanning(false)
      },
    })
  }

  async function handleCancelScan() {
    const jobId = jobIdRef.current
    if (!jobId) return
    const generation = generationRef.current

    // Stop the routine poll and cut off whatever tick of it is already in
    // flight — the centralized abortKey pattern lets this happen without
    // holding onto that tick's own AbortController.
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    abortRequest(scanStatusAbortKey(jobId))
    setCancelling(true)

    try {
      await apiFetch(`/api/v1/software/scan/${jobId}/cancel`, { method: 'POST' })
    } catch (err) {
      if (generationRef.current !== generation) return
      // 404/409 mean the scan already reached a terminal state on its own
      // (finished or someone else cancelled it) — not a cancellation failure,
      // just resume polling below to pick up whatever it actually finished as.
      if (!(err instanceof ApiError && (err.status === 404 || err.status === 409))) {
        setError(err instanceof ApiError ? err.detail : 'Failed to cancel scan — it may still be running.')
        setCancelling(false)
        return
      }
    }

    if (generationRef.current !== generation) return
    setCancelling(false)
    // The cancel endpoint only flags the loop — it doesn't wait for the
    // background task to actually stop. Resume polling so the UI reflects
    // the real 'cancelled' transition once _run_scan's next check-in notices,
    // rather than declaring victory the instant the request returns.
    startStatusPoll(jobId, generation)
  }

  async function handleImport(selectedPaths: string[]) {
    const generation = ++generationRef.current
    setImporting(true)
    setError(null)
    let result: ImportResult | null = null
    // Backend no longer has a preview cache to read titles/era from — the
    // client submits {path, title, era} per item, sourced from this hook's own
    // (already-fetched) preview list.
    const previewByPath = new Map((status?.preview ?? []).map((p) => [p.file_path, p]))
    const selected = selectedPaths.map((path) => {
      const p = previewByPath.get(path)
      return { path, title: p?.title ?? path, era: p?.detected_era ?? undefined }
    })
    try {
      result = await apiFetch<ImportResult>('/api/v1/software/scan/import', {
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

  return {
    scanning, status, error, handleScan, handleCancelScan, cancelling,
    importing, importResult, handleImport,
  }
}
