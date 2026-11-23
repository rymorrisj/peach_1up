import type { MetadataJobStatus } from '@/hooks/useMetadataApplyJob';

interface FetchApplyStepProps {
  status: MetadataJobStatus;
  cancelError: string | null;
}

function headline(status: MetadataJobStatus): string {
  switch (status.state) {
    case 'queued':
      return 'Waiting to start';
    case 'running':
      return status.cancel_requested ? 'Cancelling' : 'Downloading images';
    case 'done':
      return status.done === 0 ? 'No new media to add' : `Added ${status.done} of ${status.total}`;
    case 'cancelled':
      return 'Cancelled. Nothing was added.';
    default:
      return 'The apply failed';
  }
}

export function FetchApplyStep({ status, cancelError }: FetchApplyStepProps) {
  const running = status.state === 'queued' || status.state === 'running';
  const percent = status.total > 0 ? Math.round((status.done / status.total) * 100) : 0;

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-neutral-100">{headline(status)}</p>

      {running && (
        <>
          <div
            role="progressbar"
            aria-label="Image downloads"
            aria-valuemin={0}
            aria-valuemax={status.total}
            aria-valuenow={status.done}
            className="h-2 w-full overflow-hidden rounded-full bg-neutral-800"
          >
            <div
              className="h-full rounded-full bg-accent transition-all duration-200"
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="text-xs text-neutral-400">
            {status.done} of {status.total} images{status.label ? `, ${status.label}` : ''}
          </p>
          <p className="text-xs text-neutral-400">
            You can close this window. The job keeps running and also shows under Activity.
          </p>
        </>
      )}

      {status.state === 'failed' && (
        <div
          role="alert"
          className="whitespace-pre-wrap break-words rounded-md border border-red-600/50 bg-red-950/30 p-3 text-sm text-red-300"
        >
          {status.error?.message ?? 'The apply failed.'}
        </div>
      )}

      {cancelError && (
        <p role="alert" className="text-sm text-red-400">
          {cancelError}
        </p>
      )}
    </div>
  );
}
