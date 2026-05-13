import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, PageHeader } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { ERA_LABELS } from '@/generated/constants'
import type { components } from '@shared/types'
type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']

export default function Detail() {
  const { id } = useParams<{ id: string }>()
  const itemId = Number(id)
  const queryClient = useQueryClient()

  const { data: item, isLoading: itemLoading } = useQuery<LibraryItem>({
    queryKey: ['library', itemId],
    queryFn: () => apiFetch<LibraryItem>(`/api/v1/library/${itemId}`),
    enabled: !isNaN(itemId),
  })

  const { data: allProfiles = [], isLoading: profilesLoading } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: launchHistory = [], refetch: refetchHistory } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', itemId],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/library/${itemId}/launches`),
    enabled: !isNaN(itemId),
  })

  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const [savingProfile, setSavingProfile] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [launching, setLaunching] = useState(false)
  const [launchError, setLaunchError] = useState<string | null>(null)
  const [launchSuccess, setLaunchSuccess] = useState(false)
  const [launchWarnings, setLaunchWarnings] = useState<string[]>([])

  // Initialise selector from item once loaded
  const effectiveProfileId = selectedProfileId ?? item?.profile_id ?? null

  // Era-matched profiles shown first; others still available with warning
  const eraProfiles = allProfiles.filter((p) => item && p.era === item.era)
  const otherProfiles = allProfiles.filter((p) => item && p.era !== item.era)
  const chosenProfile = allProfiles.find((p) => p.id === effectiveProfileId) ?? null

  async function handleSaveProfile(profileId: number | null) {
    setSavingProfile(true)
    setSaveError(null)
    try {
      await apiFetch(`/api/v1/library/${itemId}`, {
        method: 'PATCH',
        body: JSON.stringify({ profile_id: profileId }),
      })
      queryClient.invalidateQueries({ queryKey: ['library', itemId] })
      queryClient.invalidateQueries({ queryKey: ['library'] })
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Failed to save profile.')
    } finally {
      setSavingProfile(false)
    }
  }

  async function handleLaunch() {
    if (!effectiveProfileId) return
    setLaunching(true)
    setLaunchError(null)
    setLaunchSuccess(false)
    setLaunchWarnings([])
    try {
      const res = await apiFetch<{ launch_history_id: number; warnings: string[] }>(
        `/api/v1/library/${itemId}/launch`,
        { method: 'POST', body: JSON.stringify({ profile_id: effectiveProfileId }) },
      )
      setLaunchSuccess(true)
      setLaunchWarnings(res.warnings ?? [])
      refetchHistory()
    } catch (err) {
      setLaunchError(err instanceof ApiError ? err.detail : 'Launch failed.')
    } finally {
      setLaunching(false)
    }
  }

  if (isNaN(itemId)) {
    return <p className="text-sm text-neutral-500">Invalid item ID.</p>
  }

  if (itemLoading || profilesLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <LoadingSpinner label="Loading…" />
        <span aria-hidden="true">Loading…</span>
      </div>
    )
  }

  if (!item) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-neutral-500">Library item not found.</p>
        <Link to="/library" className="text-sm text-[#ff8a5c] hover:underline">
          ← Back to Library
        </Link>
      </div>
    )
  }

  const eraLabel = ERA_LABELS[item.era] ?? (item.era === 'unknown' ? 'Unknown' : item.era)
  const hasProfile = effectiveProfileId != null

  return (
    <>
      <PageHeader
        title={item.title}
        description={
          <Link to="/library" className="text-sm text-[#ff8a5c] hover:underline">
            ← Library
          </Link>
        }
      />

      <div className="max-w-xl space-y-8">
        {/* Meta */}
        <section className="space-y-1 text-sm text-neutral-600 dark:text-neutral-300">
          <div>
            <span className="font-medium">Era:</span> {eraLabel}
          </div>
          <div className="flex items-start gap-1">
            <span className="font-medium shrink-0">Path:</span>
            <span className="break-all font-mono text-xs text-neutral-500 dark:text-neutral-400">
              {item.media_path}
            </span>
          </div>
          {item.launch_count > 0 && (
            <div>
              <span className="font-medium">Launches:</span> {item.launch_count}
              {item.last_launched_at && (
                <> · Last {new Date(item.last_launched_at).toLocaleDateString()}</>
              )}
            </div>
          )}
        </section>

        {/* Profile selector */}
        <section>
          <h2 className="mb-1 text-base font-semibold text-neutral-900 dark:text-neutral-100">
            Launch Profile
          </h2>
          <p className="mb-3 text-sm text-neutral-500 dark:text-neutral-400">
            Select the emulator configuration to use when launching this item.
            Launch is blocked until a profile is assigned.
          </p>

          <div className="space-y-2">
            <select
              value={effectiveProfileId ?? ''}
              onChange={(e) => {
                const val = e.target.value ? Number(e.target.value) : null
                setSelectedProfileId(val)
              }}
              className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
            >
              <option value="">— No profile selected —</option>
              {eraProfiles.length > 0 && (
                <optgroup label={`Matching era (${eraLabel})`}>
                  {eraProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}{p.is_bundled ? ' (default)' : ''}
                    </option>
                  ))}
                </optgroup>
              )}
              {otherProfiles.length > 0 && (
                <optgroup label="Other eras">
                  {otherProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({ERA_LABELS[p.era] ?? p.era})
                    </option>
                  ))}
                </optgroup>
              )}
            </select>

            {chosenProfile && item && chosenProfile.era !== item.era && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                Warning: the selected profile targets {ERA_LABELS[chosenProfile.era] ?? chosenProfile.era}, not {eraLabel}. Launch may fail or produce unexpected results.
              </p>
            )}

            {selectedProfileId !== (item.profile_id ?? null) && (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => handleSaveProfile(selectedProfileId)}
                  loading={savingProfile}
                >
                  Save profile selection
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSelectedProfileId(item.profile_id ?? null)}
                  disabled={savingProfile}
                >
                  Discard
                </Button>
              </div>
            )}

            {saveError && (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                ❌ {saveError}
              </p>
            )}
          </div>
        </section>

        {/* Launch */}
        <section>
          <Button
            onClick={handleLaunch}
            loading={launching}
            disabled={!hasProfile || launching}
            className="w-full justify-center py-3 text-base"
          >
            {hasProfile ? 'Launch' : 'Assign a profile to launch'}
          </Button>

          {!hasProfile && (
            <p className="mt-2 text-center text-xs text-neutral-400 dark:text-neutral-500">
              Select a profile above and save it to enable the launch button.
            </p>
          )}

          {launchSuccess && (
            <p className="mt-2 text-center text-sm text-green-600 dark:text-green-400">
              Launch started. The emulator should open shortly.
            </p>
          )}

          {launchWarnings.length > 0 && (
            <ul className="mt-2 space-y-1">
              {launchWarnings.map((w, i) => (
                <li key={i} className="text-center text-xs text-amber-600 dark:text-amber-400">
                  ⚠ {w}
                </li>
              ))}
            </ul>
          )}

          {launchError && (
            <p role="alert" className="mt-2 text-center text-sm text-red-600 dark:text-red-400">
              ❌ {launchError}
            </p>
          )}
        </section>

        {/* Session history */}
        {launchHistory.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
              Session History
            </h2>
            <div className="divide-y divide-neutral-100 dark:divide-neutral-800 rounded-md border border-neutral-200 dark:border-neutral-700 text-sm">
              {launchHistory.map((h) => {
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
                  <div
                    key={h.id}
                    className="flex flex-wrap items-start gap-x-4 gap-y-1 px-3 py-2"
                  >
                    <span className="min-w-[7rem] text-neutral-500 dark:text-neutral-400 tabular-nums">
                      {started.toLocaleDateString()} {started.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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

                    {h.sandboxed && h.sandbox_cpu_limit_percent != null && (
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        CPU {h.sandbox_cpu_limit_percent}%
                      </span>
                    )}

                    {h.sandboxed && h.sandbox_memory_limit_mb != null && (
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        RAM {h.sandbox_memory_limit_mb} MB
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
        )}
      </div>
    </>
  )
}
