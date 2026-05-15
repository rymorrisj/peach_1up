import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

type LaunchRecord = components['schemas']['LaunchHistoryRead']

interface LaunchHistoryProps {
  targetId: number
  targetType: 'library_item' | 'environment'
}

export default function LaunchHistory({ targetId, targetType }: LaunchHistoryProps) {
  const { data: history = [] } = useQuery<LaunchRecord[]>({
    queryKey: ['launches', targetType, targetId],
    queryFn: () =>
      apiFetch<LaunchRecord[]>(
        `/api/v1/launches?target_id=${targetId}&target_type=${encodeURIComponent(targetType)}`,
      ),
  })

  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  if (history.length === 0) return null

  function toggleExpand(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Session History
      </h4>
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
          const isExpanded = expandedIds.has(h.id)

          return (
            <div key={h.id} className="px-3 py-2">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
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
                  <span className="ml-auto text-xs text-neutral-400 dark:text-neutral-500">
                    {duration}
                  </span>
                )}
                {isError && (
                  <button
                    type="button"
                    onClick={() => toggleExpand(h.id)}
                    className="text-xs text-red-600 dark:text-red-400 hover:underline"
                    aria-expanded={isExpanded}
                  >
                    exit {h.exit_code} {isExpanded ? '▲' : '▼'}
                  </button>
                )}
              </div>
              {isError && isExpanded && h.error_message && (
                <p className="mt-1 break-all text-xs text-red-500 dark:text-red-400">
                  {h.error_message}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
