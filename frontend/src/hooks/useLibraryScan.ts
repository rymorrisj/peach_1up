import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useAppContext } from '@/context/useAppContext'
import type { BackgroundJob } from '@/context/_AppContext'

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

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  useEffect(() => {
    if (!open) {
      setScanning(false)
      setStatus(null)
      setError(null)
      setImporting(false)
      setImportResult(null)
      if (pollRef.current) clearInterval(pollRef.current)
    } else {
      // Hydrate an already-finished background scan's preview so reopening the
      // modal (e.g. from the Activity bell) shows results without re-scanning.
      // The preview no longer lives behind /scan/status (stateless now) — it's
      // read from the most recent finished scan job's result instead.
      apiFetch<BackgroundJob[]>('/api/v1/jobs')
        .then((allJobs) => {
          const lastScan = [...allJobs].reverse().find((j) => j.kind === 'scan' && j.status === 'done')
          const preview = (lastScan?.result as ScanJobResult | undefined)?.preview ?? []
          if (preview.length > 0) setStatus({ running: false, preview, error: null })
        })
        .catch(() => {})
    }
  }, [open])

  const scanMutation = useMutation<ScanTriggerResponse, Error>({
    mutationFn: () => apiFetch<ScanTriggerResponse>('/api/v1/library/scan', { method: 'POST' }),
    onSuccess: (resp) => {
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
      pollRef.current = setInterval(async () => {
        try {
          const s = await apiFetch<ScanStatusResponse>('/api/v1/library/scan/status')
          if (!s.running) {
            clearInterval(pollRef.current!)
            setScanning(false)
            if (s.error) {
              setStatus({ running: false, preview: [], error: s.error })
            } else if (jobId) {
              // The finished scan's preview lives in the job result, not on
              // this status endpoint (which is now stateless).
              const job = await apiFetch<{ result?: ScanJobResult }>(`/api/v1/jobs/${jobId}`)
              setStatus({ running: false, preview: job.result?.preview ?? [], error: null })
            } else {
              setStatus({ running: false, preview: [], error: null })
            }
          }
        } catch {
          clearInterval(pollRef.current!)
          setScanning(false)
        }
      }, 1000)
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Scan failed.')
      setScanning(false)
    },
  })

  function handleScan() {
    setError(null)
    setStatus(null)
    setImportResult(null)
    setScanning(true)
    scanMutation.mutate()
  }

  async function handleImport(selectedPaths: string[]) {
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
      })
      setImportResult(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Import failed.')
    } finally {
      setImporting(false)
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
