import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, ApiError } from '@/api/client';
import { useAppContext } from '@/context/useAppContext';
import { useToast } from '@/ui/ToastProvider';

const JOBS_PATH = '/api/v1/game-items/metadata-jobs';
const POLL_MS = 1000;
const MAX_POLL_FAILURES = 5;

export type MetadataJobState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

/** Status of an Accept All job (accept_all_job.status in the backend). */
export interface MetadataJobStatus {
  job_id: string;
  state: MetadataJobState;
  done: number;
  total: number;
  label: string | null;
  error: { code: string; message: string } | null;
  cancel_requested: boolean;
}

export function isMetadataJobActive(status: MetadataJobStatus | null): boolean {
  return status != null && (status.state === 'queued' || status.state === 'running');
}

interface Options {
  gameTitle: string;
  /** Runs once when the job reaches done, to refresh whatever shows the game or its media. */
  onApplied: () => void;
}

/**
 * Tracks one Accept All job from the moment the accept route answers 202. It
 * polls the owner-only status route, registers the job with the Activity bell
 * (whose own poll of GET /api/v1/jobs keeps it current if the page goes
 * away), and reports the outcome with a toast. It lives in the component that
 * hosts the modal, so closing the modal does not stop it.
 */
export function useMetadataApplyJob({ gameTitle, onApplied }: Options) {
  const { dispatch } = useAppContext();
  const { showToast } = useToast();
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<MetadataJobStatus | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const latest = useRef({ gameTitle, onApplied, showToast });
  useEffect(() => {
    latest.current = { gameTitle, onApplied, showToast };
  });

  const active = isMetadataJobActive(status);

  useEffect(() => {
    if (!jobId || !active) return;
    let stopped = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;

    const finish = (next: MetadataJobStatus) => {
      const { gameTitle: title, onApplied: applied, showToast: toast } = latest.current;
      setStatus(next);
      if (next.state === 'done') {
        applied();
        if (next.done === 0) toast('No new media to add', 'info');
        else toast(`Fetched images added to "${title}".`, 'success');
      } else if (next.state === 'failed') {
        toast(next.error?.message ?? 'Applying the fetched images failed.', 'error');
      } else {
        toast('Cancelled. Nothing was added.', 'info');
      }
    };

    const lost = (message: string) =>
      finish({
        job_id: jobId,
        state: 'failed',
        done: 0,
        total: 0,
        label: null,
        error: { code: 'status_unavailable', message },
        cancel_requested: false,
      });

    const tick = async () => {
      try {
        const next = await apiFetch<MetadataJobStatus>(`${JOBS_PATH}/${jobId}`);
        if (stopped) return;
        failures = 0;
        if (next.state === 'done' || next.state === 'failed' || next.state === 'cancelled') {
          finish(next);
          return;
        }
        setStatus(next);
      } catch (err) {
        if (stopped) return;
        failures += 1;
        if (err instanceof ApiError && err.status === 404) {
          lost(
            'The server no longer knows this job, it may have restarted. Check the game media, then retry.',
          );
          return;
        }
        if (failures >= MAX_POLL_FAILURES) {
          lost(
            'Lost contact with the server while the job was running. It may still finish, check Activity.',
          );
          return;
        }
      }
      timer = setTimeout(tick, POLL_MS);
    };

    timer = setTimeout(tick, POLL_MS);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId, active]);

  const track = useCallback(
    (id: string, total: number) => {
      setJobId(id);
      setCancelError(null);
      setStatus({
        job_id: id,
        state: 'queued',
        done: 0,
        total,
        label: null,
        error: null,
        cancel_requested: false,
      });
      dispatch({
        type: 'UPSERT_JOB',
        payload: {
          id,
          kind: 'metadata_apply',
          status: 'processing',
          progress: 0,
          message: 'Applying fetched images',
        },
      });
    },
    [dispatch],
  );

  const cancel = useCallback(async () => {
    if (!jobId) return;
    setCancelError(null);
    try {
      const next = await apiFetch<MetadataJobStatus>(`${JOBS_PATH}/${jobId}/cancel`, {
        method: 'POST',
      });
      setStatus((prev) => (isMetadataJobActive(prev) && isMetadataJobActive(next) ? next : prev));
    } catch (err) {
      // 404 and 409 mean the job already ended; the next poll reports how.
      if (!(err instanceof ApiError && (err.status === 404 || err.status === 409))) {
        setCancelError(err instanceof Error ? err.message : 'Could not cancel the job.');
      }
    }
  }, [jobId]);

  const reset = useCallback(() => {
    setJobId(null);
    setStatus(null);
    setCancelError(null);
  }, []);

  return { status, active, cancelError, track, cancel, reset };
}
