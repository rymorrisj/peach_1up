import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { Button } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useLaunch } from '@/hooks/useLaunch'
import { ERA_LABELS } from '@/generated/constants'
import type { LibrarySetData } from './components/SetCard'

export default function SetDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const setId = Number(id)

  const { data: set, isLoading } = useQuery({
    queryKey: ['library', 'sets', setId],
    queryFn: () => apiFetch<LibrarySetData>(`/api/v1/library/sets/${setId}`),
    enabled: !isNaN(setId),
  })

  const { launch, isLaunching, error: launchError, launchSuccess, launchWarnings } = useLaunch({
    targetId: setId,
    targetType: 'set',
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <LoadingSpinner label="Loading…" />
        <span aria-hidden="true">Loading…</span>
      </div>
    )
  }

  if (!set) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-neutral-500">Set not found.</p>
        <Link to="/library" className="text-sm text-[#ff8a5c] hover:underline">
          ← Back to Library
        </Link>
      </div>
    )
  }

  const eraLabel = ERA_LABELS[set.era] ?? (set.era === 'unknown' ? 'Unknown' : set.era)
  const sortedItems = set.items.slice().sort((a, b) => a.disc_number - b.disc_number)
  // ps1 → DuckStation, ps2 → PCSX2: disc swap is manual via emulator's in-app menu
  const showDiscSwapWarning = (set.era === 'ps1' || set.era === 'ps2') && sortedItems.length > 1

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title={set.title} />

      <div className="p-6">
        <div className="mb-6">
          <Link to="/library" className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
            ← Library
          </Link>
        </div>

        <div className="max-w-xl space-y-10">

          <section className="space-y-1 text-sm text-neutral-600 dark:text-neutral-300">
            <div>
              <span className="font-medium">Era:</span> {eraLabel}
            </div>
            <div>
              <span className="font-medium">Discs:</span> {set.items.length}
            </div>
            {set.launch_count > 0 && (
              <div>
                <span className="font-medium">Launches:</span> {set.launch_count}
                {set.last_launched_at && (
                  <> · Last {new Date(set.last_launched_at + 'Z').toLocaleDateString()}</>
                )}
              </div>
            )}
          </section>

          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Discs
            </h2>
            <ul className="space-y-1.5">
              {sortedItems.map((disc) => {
                const isLaunch = disc.id === set.launch_disk_id
                const filename = disc.media_path.split(/[\\/]/).pop() ?? disc.media_path
                return (
                  <li
                    key={disc.id}
                    className="flex items-center gap-3 rounded-md border border-neutral-700 bg-neutral-800/40 px-3 py-2 text-sm"
                  >
                    <span className="w-5 shrink-0 font-mono text-xs text-neutral-500">{disc.disc_number}</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-xs text-neutral-400">{filename}</span>
                    {isLaunch && (
                      <span className="shrink-0 rounded-[4px] border border-[#ff8a5c]/40 bg-[#ff8a5c]/10 px-1.5 py-0.5 font-mono text-[10px] text-[#ff8a5c]">
                        Launch disc
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>

          {showDiscSwapWarning && (
            <div
              role="note"
              className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3"
            >
              <div className="flex items-center gap-2 font-medium text-sm text-amber-600 dark:text-amber-400 mb-1">
                <span aria-hidden="true">⚠</span>
                Manual disc swap required
              </div>
              <p className="text-xs text-amber-700/80 dark:text-amber-400/80 leading-relaxed">
                Discs must be swapped manually using the emulator's own disc-swap menu (e.g.{' '}
                <span className="font-mono">System → Change Disc</span>) once the game is running.
                Peach 1UP does not automate disc swapping for console platforms.
              </p>
            </div>
          )}

          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Launch
            </h2>
            <Button
              onClick={() => launch(set.profile_id)}
              loading={isLaunching}
              disabled={isLaunching}
              className="w-full justify-center py-3 text-base"
            >
              Launch
            </Button>

            {launchSuccess && (
              <p className="text-center text-sm text-green-600 dark:text-green-400">
                Launch started. The emulator should open shortly.
              </p>
            )}

            {launchWarnings.map((w, i) => (
              <p key={i} className="text-center text-xs text-amber-600 dark:text-amber-400">
                ⚠ {w}
              </p>
            ))}

            {launchError && (
              <p role="alert" className="text-center text-sm text-red-600 dark:text-red-400">
                ❌ {launchError}
              </p>
            )}
          </section>

        </div>
      </div>
    </div>
  )
}
