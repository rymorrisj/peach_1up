import type { components } from '@shared/types'

type LaunchHistory = components['schemas']['LaunchHistoryRead']

interface LaunchHistorySectionProps {
  history: LaunchHistory[]
}

export function LaunchHistorySection({ history }: LaunchHistorySectionProps) {
  if (history.length === 0) return null

  return (
    <section className="space-y-2">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Session History
      </h2>
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
