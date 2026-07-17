import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type LaunchHistory = components['schemas']['LaunchHistoryRead']

interface LaunchHistorySectionProps {
  history: LaunchHistory[]
  /** Owner/admin only: enables checkbox selection and the delete action.
   *  Deletion is enforced owner/admin on the backend regardless. */
  canDelete?: boolean
}

export function LaunchHistorySection({ history, canDelete = false }: LaunchHistorySectionProps) {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (history.length === 0) return null

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleDelete() {
    if (selected.size === 0) return
    setDeleting(true)
    setError(null)
    try {
      // One endpoint for both "delete this one" (a single checked row) and
      // "delete these N". Invalidate the shared 'launches' key prefix so every
      // launch-history view (this section, the per-target list, the TopBar
      // recent list) refetches.
      await apiFetch('/api/v1/launches', {
        method: 'DELETE',
        body: JSON.stringify({ ids: Array.from(selected) }),
      })
      setSelected(new Set())
      await queryClient.invalidateQueries({ queryKey: ['launches'] })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete history.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
          Session History
        </h2>
        {canDelete && selected.size > 0 && (
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="ml-auto rounded-md border border-red-500/40 px-2.5 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400"
          >
            Delete selected ({selected.size})
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
      <div className="divide-y divide-neutral-100 dark:divide-neutral-800 rounded-md border border-neutral-200 dark:border-neutral-700 text-sm">
        {history.map((h) => {
          const started = new Date(h.started_at)
          const durationMs = h.ended_at
            ? new Date(h.ended_at).getTime() - started.getTime()
            : null
          const duration =
            durationMs != null
              ? durationMs < 60_000
                ? `${Math.round(durationMs / 1000)}s`
                : `${Math.floor(durationMs / 60_000)}m ${Math.round((durationMs % 60_000) / 1000)}s`
              : null
          const isError = h.exit_code != null && h.exit_code !== 0

          return (
            <div key={h.id} className="flex flex-wrap items-start gap-x-4 gap-y-1 px-3 py-2">
              {canDelete && (
                <input
                  type="checkbox"
                  checked={selected.has(h.id)}
                  onChange={() => toggle(h.id)}
                  aria-label={`Select launch ${h.id} for deletion`}
                  className="mt-0.5 h-4 w-4 shrink-0 accent-accent"
                />
              )}
              <span className="min-w-[7rem] text-neutral-500 dark:text-neutral-400 tabular-nums">
                {started.toLocaleDateString()}{' '}
                {started.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              <span className="font-mono text-xs text-neutral-400 dark:text-neutral-500 self-center">
                {h.emulator_slug}
              </span>
              {h.sandboxed ? (
                <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  sandboxed
                </span>
              ) : (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                  not sandboxed
                </span>
              )}
              {duration && (
                <span className="text-xs text-neutral-400 dark:text-neutral-500 ml-auto">
                  {duration}
                </span>
              )}
              {isError && (
                <span className="w-full text-xs text-red-600 dark:text-red-400 truncate">
                  exit {h.exit_code}{h.error_message ? ` · ${h.error_message}` : ''}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
