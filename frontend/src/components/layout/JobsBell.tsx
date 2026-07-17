import { useState } from 'react'
import { Bell, X } from 'lucide-react'
import { Button, Modal } from '@/ui'
import { useAppContext } from '@/context/useAppContext'
import type { BackgroundJob } from '@/context/_AppContext'

// 'cancelling' is still in-flight work from the user's point of view — the
// job hasn't reached a terminal state yet, it's just winding down — so it's
// grouped with 'processing' everywhere "still running" is checked below.
const isActiveStatus = (status: BackgroundJob['status']) => status === 'processing' || status === 'cancelling'

function JobRow({ job, onDismiss }: { job: BackgroundJob; onDismiss: (id: string) => void }) {
  const pct = Math.round((job.progress ?? 0) * 100)
  const kindLabel = job.kind === 'scan' ? 'Library scan' : 'Upload'
  const color =
    job.status === 'error' ? 'rgb(var(--error))' : job.status === 'done' ? 'rgb(var(--success))' : 'rgb(var(--peach-500))'
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
            style={{ color: 'rgb(var(--fg-3))', background: 'none', border: 'none', cursor: 'pointer' }}
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
  )
}

export default function JobsBell() {
  const { state, dispatch } = useAppContext()
  const [open, setOpen] = useState(false)

  const jobs = state.backgroundJobs
  if (jobs.length === 0) return null

  const active = jobs.filter((j) => isActiveStatus(j.status)).length

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative flex items-center gap-2 rounded-lg px-3 py-[7px] text-sm font-medium transition-colors hover:text-fg-1"
        style={{ fontFamily: 'var(--font-display)', color: 'rgb(var(--fg-2))', background: 'transparent', border: 'none', cursor: 'pointer', width: '100%' }}
        aria-label="Background activity"
      >
        <span className="relative w-[18px] text-center" aria-hidden="true">
          <Bell size={16} />
          {active > 0 && (
            <span
              className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full px-1 text-[0.5625rem] font-bold"
              style={{ background: 'rgb(var(--peach-500))', color: '#1d0a04', animation: 'dot-pulse 1.4s ease-in-out infinite' }}
            >
              {active}
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
              <JobRow key={job.id} job={job} onDismiss={(id) => dispatch({ type: 'DISMISS_JOB', payload: id })} />
            ))}
          </ul>
        )}
      </Modal>
    </>
  )
}
