import { useState, useEffect, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { apiFetch, ApiError, TimeoutError } from '@/api/client';
import { useAppContext } from '@/context/useAppContext';
import type { BackgroundJob } from '@/context/_AppContext';

// The import endpoint is a synchronous, unbatched loop over every selected
// item (DB lookups + a shutil.move of the actual media file, which can be a
// slow cross-device copy for large ROM/ISO files, plus a commit per item) —
// there's no background job/status polling for it like there is for the scan
// itself, so the whole batch has to finish inside one HTTP request. Give it
// much more room than apiFetch's 10s default so a handful of large files
// doesn't get mislabeled as a failure while still importing server-side.
const IMPORT_TIMEOUT_MS = 120_000;

export interface ScanPreviewItem {
  title: string;
  file_path: string;
  detected_era: string | null;
  is_loose: boolean;
  is_zip: boolean;
}

// Client-composed view model: the backend's GET /library/scan/status no longer
// carries a preview (scan is stateless, the only copy of a finished scan's
// results lives in its core.jobs result payload), so `preview` here is filled
// in from the job result rather than passed through directly from that endpoint.
export interface ScanStatus {
  running: boolean;
  preview: ScanPreviewItem[];
  error: string | null;
  /** True when this status reflects a user-cancelled scan rather than a
   *  normal completion or a real error. */
  cancelled?: boolean;
}

interface ScanJobResult {
  preview?: ScanPreviewItem[];
}

export interface ImportResult {
  imported: number;
  skipped: number;
  errors: Array<{ path: string; reason: string }>;
}

interface UseLibraryScanOptions {
  open: boolean;
  onImported: () => void;
}

interface ScanTriggerResponse {
  started: boolean;
  directory: string;
  job_id?: string;
}

export function useLibraryScan({ open, onImported }: UseLibraryScanOptions) {
  const { state, dispatch } = useAppContext();
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [cancelling, setCancelling] = useState(false);
  // Current scan's job id, so handleCancelScan (fired from a separate click,
  // not from inside the mutation's own onSuccess closure) knows what to cancel,
  // and so render can look up the job's live progress in state.backgroundJobs.
  // State rather than a ref: its value is read during render (below), and refs
  // must not be read outside effects/handlers.
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Monotonic "generation" counter. Every new scan/import operation bumps
  // this, and so does the reset effect below, once a close finds nothing
  // still running. Any async callback (mutation onSuccess/onError, the
  // status poll, the job-hydration fetch, handleImport's own await) captures
  // the value current at its own start and re-checks it before writing
  // state; if the value has moved on, that callback has been superseded and
  // becomes a no-op instead of clobbering newer state.
  //
  // This matters because Games.tsx always keeps <LibraryModal> (scan mode)
  // mounted (only toggles `open`), so this hook instance, and any in-flight
  // promise's closures, stay alive across opens/closes. Modal.tsx blocks
  // Escape while busy, and the Cancel button is disabled during import, but
  // scanning can be dismissed early once a job exists (the scan continues as
  // a tracked background job). A user can dismiss mid-scan, reopen, run a
  // second scan/import that succeeds, and then have the first (now-stale)
  // operation's catch/then fire afterward and overwrite the freshly-
  // successful UI state. The generation guard makes that stale completion
  // inert.
  const generationRef = useRef(0);

  // Only resets once this hook's own scan/import has actually finished, not
  // merely whenever the modal closes. A scan (or import) still in flight
  // keeps running as a tracked background job regardless of this modal's
  // open state (see the busy comment in ScanBody), so resetting scanning/
  // activeJobId just because the user dismissed (now possible via Escape/
  // overlay once activeJobId exists, not only the Hide button) would orphan
  // this hook's only link to that job and make a reopen show the blank
  // "before scan" screen instead of live progress, even though the
  // terminal-resolution effect below keeps resolving it correctly in the
  // background either way.
  useEffect(() => {
    if (open || scanning || importing) return;
    generationRef.current += 1;
    setScanning(false);
    setStatus(null);
    setError(null);
    setImporting(false);
    setImportResult(null);
    setCancelling(false);
    setActiveJobId(null);
  }, [open, scanning, importing]);

  useEffect(() => {
    if (!open) return;
    const generation = generationRef.current;
    // Hydrate an already-finished background scan's preview so reopening the
    // modal (e.g. from the Activity bell) shows results without re-scanning.
    // The preview no longer lives behind /scan/status (stateless now), it's
    // read from the most recent finished scan job's result instead.
    apiFetch<BackgroundJob[]>('/api/v1/jobs')
      .then((allJobs) => {
        if (generationRef.current !== generation) return;
        const lastScan = [...allJobs]
          .reverse()
          .find((j) => j.kind === 'scan' && j.status === 'done');
        const preview = (lastScan?.result as ScanJobResult | undefined)?.preview ?? [];
        if (preview.length > 0) setStatus({ running: false, preview, error: null });
      })
      .catch(() => {});
  }, [open]);

  const scanMutation = useMutation<ScanTriggerResponse, Error>({
    mutationFn: () => apiFetch<ScanTriggerResponse>('/api/v1/game-items/scan', { method: 'POST' }),
  });

  // Live entry for the in-flight scan job, sourced from the shared job store
  // (AppContext's own 1500ms poll of GET /api/v1/jobs, already running for any
  // processing/cancelling job) instead of a second, separate poll of the
  // now-stateless /scan/status endpoint. Recomputed on every render, so it
  // tracks the job's real progress/message as AppContext's poll updates them.
  const activeScanJob = activeJobId
    ? state.backgroundJobs.find((j) => j.id === activeJobId)
    : undefined;
  const scanProgress = activeScanJob ? Math.round((activeScanJob.progress ?? 0) * 100) : 0;
  const scanMessage = activeScanJob?.message ?? null;

  // Resolves the tracked scan job once it reaches a terminal state (done,
  // error, or cancelled). activeJobId is cleared immediately after resolving
  // so this effect only fires setStatus once per scan, rather than on every
  // subsequent AppContext poll tick while other jobs stay active (which would
  // otherwise hand ScanBody a new `status` object each tick and re-trigger its
  // "auto-select all" effect, wiping manual deselections).
  // Self-terminating via the activeJobId guard (cleared as soon as this
  // fires, so it can't refire for the same job), so this is adjusted during
  // render rather than in a useEffect: purely local setState calls reacting
  // to the shared job store, no external side effect attached.
  if (activeJobId) {
    const job = state.backgroundJobs.find((j) => j.id === activeJobId);
    if (job && job.status !== 'processing' && job.status !== 'cancelling') {
      setActiveJobId(null);
      setScanning(false);
      if (job.status === 'cancelled') {
        setStatus({ running: false, preview: [], error: null, cancelled: true });
      } else if (job.status === 'error') {
        setStatus({ running: false, preview: [], error: job.error ?? 'Scan failed.' });
      } else {
        const result = job.result as ScanJobResult | undefined;
        setStatus({ running: false, preview: result?.preview ?? [], error: null });
      }
    }
  }

  function handleScan() {
    const generation = ++generationRef.current;
    setError(null);
    setStatus(null);
    setImportResult(null);
    setScanning(true);
    setActiveJobId(null);
    scanMutation.mutate(undefined, {
      onSuccess: (resp) => {
        if (generationRef.current !== generation) return;
        setScanning(true);
        const jobId = resp?.job_id;
        setActiveJobId(jobId ?? null);
        if (jobId) {
          // Surface the scan in the nav-bell Activity panel; for a large
          // (background) scan the user can close this modal and watch it there.
          dispatch({
            type: 'UPSERT_JOB',
            payload: {
              id: jobId,
              kind: 'scan',
              status: 'processing',
              progress: 0,
              message: 'Scanning media library…',
            },
          });
        }
      },
      onError: (err) => {
        if (generationRef.current !== generation) return;
        setError(err instanceof ApiError ? err.detail : 'Scan failed.');
        setScanning(false);
      },
    });
  }

  async function handleCancelScan() {
    const jobId = activeJobId;
    if (!jobId) return;
    const generation = generationRef.current;
    setCancelling(true);

    try {
      await apiFetch(`/api/v1/game-items/scan/${jobId}/cancel`, { method: 'POST' });
    } catch (err) {
      if (generationRef.current !== generation) return;
      // 404/409 mean the scan already reached a terminal state on its own
      // (finished or someone else cancelled it), not a cancellation failure,
      // the terminal-resolution effect above will pick up whatever it
      // actually finished as via the shared job store.
      if (!(err instanceof ApiError && (err.status === 404 || err.status === 409))) {
        setError(
          err instanceof ApiError ? err.detail : 'Failed to cancel scan, it may still be running.',
        );
        setCancelling(false);
        return;
      }
    }

    if (generationRef.current !== generation) return;
    setCancelling(false);
    // The cancel endpoint only flags the loop, it doesn't wait for the
    // background task to actually stop. activeJobId stays set, so the
    // terminal-resolution effect above will reflect the real 'cancelled'
    // transition once _run_scan's next check-in notices and AppContext's
    // shared poll picks it up, rather than declaring victory here.
  }

  async function handleImport(selectedPaths: string[]) {
    const generation = ++generationRef.current;
    setImporting(true);
    setError(null);
    let result: ImportResult | null = null;
    // Backend no longer has a preview cache to read titles/era from, the
    // client submits {path, title, era} per item, sourced from this hook's own
    // (already-fetched) preview list.
    const previewByPath = new Map((status?.preview ?? []).map((p) => [p.file_path, p]));
    const selected = selectedPaths.map((path) => {
      const p = previewByPath.get(path);
      return { path, title: p?.title ?? path, era: p?.detected_era ?? undefined };
    });
    try {
      result = await apiFetch<ImportResult>('/api/v1/game-items/scan/import', {
        method: 'POST',
        body: JSON.stringify({ selected }),
        timeoutMs: IMPORT_TIMEOUT_MS,
      });
      // A newer scan/import cycle may have started while this request was in
      // flight (e.g. the user Escape-closed the dialog, which bypasses the
      // Cancel button's disabled={busy} guard, then reopened and ran another
      // import). If so, this call is superseded: applying its result now
      // would stomp whatever the newer, current operation already rendered.
      if (generationRef.current === generation) setImportResult(result);
    } catch (err) {
      if (generationRef.current === generation) {
        setError(
          err instanceof ApiError
            ? err.detail
            : err instanceof TimeoutError
              ? 'Import is taking longer than expected, check your library, it may still be processing.'
              : 'Import failed.',
        );
      }
    } finally {
      if (generationRef.current === generation) setImporting(false);
    }
    // Runs outside the fetch's try/catch: onImported() is a cache-invalidation
    // side effect unrelated to the import call itself, and must never be able
    // to retroactively overwrite an already-successful importResult with an
    // unrelated "Import failed" error.
    if (result && result.imported > 0) {
      try {
        onImported();
      } catch (err) {
        console.error('onImported callback failed after a successful import:', err);
      }
    }
  }

  return {
    scanning,
    status,
    error,
    handleScan,
    handleCancelScan,
    cancelling,
    importing,
    importResult,
    handleImport,
    scanProgress,
    scanMessage,
    // Exposed so ScanBody can narrow its own Modal dismiss gate to "no job
    // yet" instead of "not finished".
    activeJobId,
  };
}
