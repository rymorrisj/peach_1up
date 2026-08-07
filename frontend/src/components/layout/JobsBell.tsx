import { useEffect, useState } from 'react';
import { Bell, X } from 'lucide-react';
import { Button, Modal } from '@/ui';
import { useAppContext } from '@/context/useAppContext';
import type { BackgroundJob } from '@/context/_AppContext';

// 'cancelling' is still in-flight work from the user's point of view, the
// job hasn't reached a terminal state yet, it's just winding down, so it's
// grouped with 'processing' everywhere "still running" is checked below.
const isActiveStatus = (status: BackgroundJob['status']) =>
  status === 'processing' || status === 'cancelling';

function JobRow({ job, onDismiss }: { job: BackgroundJob; onDismiss: (id: string) => void }) {
  const pct = Math.round((job.progress ?? 0) * 100);
  const kindLabel = job.kind === 'scan' ? 'Library scan' : 'Upload';
  const color =
    job.status === 'error'
      ? 'rgb(var(--error))'
      : job.status === 'done'
        ? 'rgb(var(--success))'
        : 'rgb(var(--peach-500))';
  return (
    <li className="rounded-md border px-3 py-2" style={{ borderColor: 'rgb(var(--border))' }}>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-sm" style={{ color: 'rgb(var(--fg-1))' }}>
          {kindLabel}
        </span>
        {!isActiveStatus(job.status) && (
          <button
            type="button"
            onClick={() => onDismiss(job.id)}
            className="shrink-0 rounded p-0.5"
            style={{
              color: 'rgb(var(--fg-3))',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
            }}
            aria-label="Dismiss"
          >
            <X size={14} />
          </button>
        )}
      </div>
      <p className="mt-0.5 truncate text-xs" style={{ color: 'rgb(var(--fg-3))' }}>
        {job.message || (job.status === 'processing' ? 'Working…' : job.status)}
      </p>
      {isActiveStatus(job.status) && (
        <div
          className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full"
          style={{ background: 'rgb(var(--surface-3))' }}
        >
          <div
            className="h-full rounded-full transition-all duration-200"
            style={{ width: `${pct}%`, background: color }}
          />
        </div>
      )}
    </li>
  );
}

export default function JobsBell() {
  const { state, dispatch } = useAppContext();
  const [open, setOpen] = useState(false);

  const jobs = state.backgroundJobs;

  // Keep the seen snapshot current while the panel stays open, so a job that
  // transitions state (e.g. finishes) while the user is actively looking at
  // the list doesn't immediately re-trigger the badge the moment they close
  // it, they were already watching it happen. Runs unconditionally (ahead of
  // the jobs.length===0 early return below) since hooks can't be called
  // conditionally.
  useEffect(() => {
    if (open) dispatch({ type: 'MARK_JOBS_SEEN' });
  }, [open, jobs, dispatch]);

  if (jobs.length === 0) return null;

  const active = jobs.filter((j) => isActiveStatus(j.status)).length;
  // A job is "unseen" when its current status differs from the snapshot
  // taken the last time the Activity panel was opened (see MARK_JOBS_SEEN),
  // this is what makes a job that finishes, success or failure, while the
  // panel is closed still surface a badge, not just jobs actively in
  // progress right now.
  const unseenJobs = jobs.filter((j) => state.seenJobStates[j.id] !== j.status);
  const unseenCount = unseenJobs.length;
  const hasUnseenError = unseenJobs.some((j) => j.status === 'error');
  const hasUnseenDone = unseenJobs.some((j) => j.status === 'done');
  // Same severity coloring JobRow already uses below (error > done > in
  // progress), reused here instead of introducing a separate badge palette.
  const badgeColor = hasUnseenError
    ? 'rgb(var(--error))'
    : hasUnseenDone
      ? 'rgb(var(--success))'
      : 'rgb(var(--peach-500))';

  function handleOpen() {
    setOpen(true);
    dispatch({ type: 'MARK_JOBS_SEEN' });
  }

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="relative flex items-center gap-2 rounded-lg px-3 py-[7px] text-sm font-medium transition-colors hover:text-fg-1"
        style={{
          fontFamily: 'var(--font-display)',
          color: 'rgb(var(--fg-2))',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          width: '100%',
        }}
        aria-label="Background activity"
      >
        <span className="relative w-[18px] text-center" aria-hidden="true">
          <Bell size={16} />
          {unseenCount > 0 && (
            <span
              className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full px-1 text-[0.5625rem] font-bold"
              style={{
                background: badgeColor,
                color: 'rgb(var(--accent-ink))',
                // Only pulse while something is actually still running, a
                // badge for a completed job sitting unseen is a static
                // notification, not a live-activity indicator.
                animation: active > 0 ? 'dot-pulse 1.4s ease-in-out infinite' : undefined,
              }}
            >
              {unseenCount}
            </span>
          )}
        </span>
        <span className="flex-1 text-left">Activity</span>
      </button>

      <Modal
        open={open}
        title="Background Activity"
        onClose={() => setOpen(false)}
        footer={<Button onClick={() => setOpen(false)}>Close</Button>}
      >
        {jobs.length === 0 ? (
          <p className="text-sm" style={{ color: 'rgb(var(--fg-3))' }}>
            No background activity.
          </p>
        ) : (
          <ul className="space-y-2">
            {jobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                onDismiss={(id) => dispatch({ type: 'DISMISS_JOB', payload: id })}
              />
            ))}
          </ul>
        )}
      </Modal>
    </>
  );
}
