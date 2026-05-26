import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Textarea } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'
import LaunchCommandList from '@/components/LaunchCommandList'
import { useAppContext } from '@/context/AppContext'
import { ERA_LABELS, RATING_OPTIONS } from '@/generated/constants'
import { ERA_TO_EMULATOR } from '@/pages/Environments/EnvironmentModal'
import type { components } from '@shared/types'
type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']
type Platform = components['schemas']['PlatformRead']
type User = components['schemas']['UserRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']

const SELECT_CLASS =
  'w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100'

interface EditForm {
  title: string
  sort_title: string
  description: string
  publisher: string
  year: string
  category: string
  cover_art_path: string
  content_rating: string
  era: string
  platform_id: string
  profile_id: string
  executable_path: string
}

function formFromItem(item: LibraryItem): EditForm {
  return {
    title: item.title,
    sort_title: item.sort_title ?? '',
    description: item.description ?? '',
    publisher: item.publisher ?? '',
    year: item.year?.toString() ?? '',
    category: item.category ?? '',
    cover_art_path: item.cover_art_path ?? '',
    content_rating: item.content_rating ?? '',
    era: item.era ?? '',
    platform_id: item.platform_id?.toString() ?? '',
    profile_id: item.profile_id?.toString() ?? '',
    executable_path: item.executable_path ?? '',
  }
}

export default function ItemDetail() {
  const { slug } = useParams<{ slug: string }>()
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()

  const isAdminOrOwner =
    (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)

  const { data: item, isLoading: itemLoading } = useQuery<LibraryItem>({
    queryKey: ['library', 'by-slug', slug],
    queryFn: () => apiFetch<LibraryItem>(`/api/v1/library/by-slug/${slug}`),
    enabled: !!slug,
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: platforms = [] } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/users'),
    enabled: isAdminOrOwner,
  })

  const { data: restrictionsData, refetch: refetchRestrictions } = useQuery<{
    restricted_user_ids: number[]
  }>({
    queryKey: ['restrictions', item?.id],
    queryFn: () =>
      apiFetch<{ restricted_user_ids: number[] }>(`/api/v1/library/${item!.id}/restrictions`),
    enabled: isAdminOrOwner && !!item,
  })

  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', item?.id],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/library/${item!.id}/launches`),
    enabled: !!item,
  })

  // ── Edit form ──
  const [form, setForm] = useState<EditForm | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (item && !form) setForm(formFromItem(item))
  }, [item, form])

  // ── Advanced ──
  const [launchCommands, setLaunchCommands] = useState<string[] | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [rescanning, setRescanning] = useState(false)
  const [rescanError, setRescanError] = useState<string | null>(null)
  const [flagging, setFlagging] = useState(false)
  const [flagError, setFlagError] = useState<string | null>(null)
  useEffect(() => {
    if (item && launchCommands === null) {
      setLaunchCommands(item.launch_commands ?? [])
    }
  }, [item, launchCommands])

  async function handleRescan() {
    if (!item) return
    setRescanning(true)
    setRescanError(null)
    try {
      const updated = await apiFetch<LibraryItem>(`/api/v1/library/${item.id}/rescan`, { method: 'POST' })
      queryClient.setQueryData(['library', 'by-slug', slug], updated)
    } catch (err) {
      setRescanError(err instanceof ApiError ? err.detail : 'Rescan failed.')
    } finally {
      setRescanning(false)
    }
  }

  async function handleFlagLaunch() {
    if (!item) return
    setFlagging(true)
    setFlagError(null)
    try {
      await apiFetch(`/api/v1/library/${item.id}/flag-launch`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setFlagError(err instanceof ApiError ? err.detail : 'Failed to flag.')
    } finally {
      setFlagging(false)
    }
  }

  function setField<K extends keyof EditForm>(key: K, value: EditForm[K]) {
    setForm((prev) => prev && { ...prev, [key]: value })
    setSaveSuccess(false)
  }

  async function handleSave() {
    if (!item || !form) return
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      await apiFetch(`/api/v1/library/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: form.title.trim() || undefined,
          sort_title: form.sort_title.trim() || null,
          description: form.description.trim() || null,
          publisher: form.publisher.trim() || null,
          year: form.year ? parseInt(form.year, 10) : null,
          category: form.category.trim() || null,
          cover_art_path: form.cover_art_path.trim() || null,
          content_rating: form.content_rating || null,
          era: form.era || null,
          platform_id: form.platform_id ? parseInt(form.platform_id, 10) : null,
          profile_id: form.profile_id ? parseInt(form.profile_id, 10) : null,
          launch_commands: launchCommands ?? item.launch_commands ?? [],
        }),
      })
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
      setSaveSuccess(true)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Failed to save.')
    } finally {
      setSaving(false)
    }
  }

  // ── Launch ──
  const [launching, setLaunching] = useState(false)
  const [launchError, setLaunchError] = useState<string | null>(null)
  const [launchSuccess, setLaunchSuccess] = useState(false)
  const [launchWarnings, setLaunchWarnings] = useState<string[]>([])
  const [activeHistoryId, setActiveHistoryId] = useState<number | null>(null)

  // Poll the active launch record until ended_at is set, then clear the success banner.
  useEffect(() => {
    if (activeHistoryId === null) return
    const intervalId = setInterval(async () => {
      try {
        const record = await apiFetch<LaunchHistory>(`/api/v1/launches/${activeHistoryId}`)
        if (record.ended_at !== null) {
          setLaunchSuccess(false)
          setActiveHistoryId(null)
          queryClient.invalidateQueries({ queryKey: ['launches', item?.id] })
        }
      } catch {
        setActiveHistoryId(null)
      }
    }, 2000)
    return () => clearInterval(intervalId)
  }, [activeHistoryId, item?.id, queryClient])

  async function handleLaunch() {
    if (!item || !form) return
    const profileId = form.profile_id ? parseInt(form.profile_id, 10) : null
    if (!profileId) return
    setLaunching(true)
    setLaunchError(null)
    setLaunchSuccess(false)
    setLaunchWarnings([])
    setActiveHistoryId(null)
    try {
      const res = await apiFetch<{ launch_history_id: number; warnings: string[] }>(
        `/api/v1/library/${item.id}/launch`,
        { method: 'POST', body: JSON.stringify({ profile_id: profileId }) },
      )
      setLaunchSuccess(true)
      setLaunchWarnings(res.warnings ?? [])
      setActiveHistoryId(res.launch_history_id)
    } catch (err) {
      setLaunchError(err instanceof ApiError ? err.detail : 'Launch failed.')
    } finally {
      setLaunching(false)
    }
  }

  // ── Restrictions ──
  const [restrictedIds, setRestrictedIds] = useState<Set<number>>(new Set())
  const [restrictionsDirty, setRestrictionsDirty] = useState(false)
  const [savingRestrictions, setSavingRestrictions] = useState(false)
  const [restrictionsError, setRestrictionsError] = useState<string | null>(null)

  useEffect(() => {
    if (restrictionsData && !restrictionsDirty) {
      setRestrictedIds(new Set(restrictionsData.restricted_user_ids))
    }
  }, [restrictionsData, restrictionsDirty])

  function toggleRestriction(userId: number) {
    setRestrictedIds((prev) => {
      const next = new Set(prev)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
    setRestrictionsDirty(true)
  }

  async function handleSaveRestrictions() {
    if (!item) return
    setSavingRestrictions(true)
    setRestrictionsError(null)
    try {
      await apiFetch(`/api/v1/library/${item.id}/restrictions`, {
        method: 'PUT',
        body: JSON.stringify({ user_ids: Array.from(restrictedIds) }),
      })
      setRestrictionsDirty(false)
      queryClient.invalidateQueries({ queryKey: ['library'] })
      refetchRestrictions()
    } catch (err) {
      setRestrictionsError(err instanceof ApiError ? err.detail : 'Failed to save restrictions.')
    } finally {
      setSavingRestrictions(false)
    }
  }

  // ── Render ──
  if (itemLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <LoadingSpinner label="Loading…" />
        <span aria-hidden="true">Loading…</span>
      </div>
    )
  }

  if (!item || !form) {
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
  const effectiveProfileId = form.profile_id ? parseInt(form.profile_id, 10) : null
  const hasProfile = effectiveProfileId != null

  const eraProfiles = profiles.filter((p) => p.era === item.era)
  const otherProfiles = profiles.filter((p) => p.era !== item.era)
  const chosenProfile = profiles.find((p) => p.id === effectiveProfileId) ?? null
  const expectedEmulator = (ERA_TO_EMULATOR as Record<string, string | undefined>)[item.era]
  const profileEraMismatch =
    chosenProfile && expectedEmulator != null && chosenProfile.emulator_slug !== expectedEmulator

  const nonOwnerUsers = users.filter((u) => !u.is_owner)

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title={item.title} />

      <div className="p-6">
        <div className="mb-6">
          <Link to="/library" className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
            ← Library
          </Link>
        </div>

        <div className="max-w-xl space-y-10">

        {/* ── Meta (read-only) ── */}
        <section className="space-y-1 text-sm text-neutral-600 dark:text-neutral-300">
          <div className="flex items-start gap-1">
            <span className="font-medium shrink-0">Slug:</span>
            <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400 self-center">
              {item.slug ?? '—'}
            </span>
          </div>
          <div className="flex items-start gap-1">
            <span className="font-medium shrink-0">Path:</span>
            <span className="break-all font-mono text-xs text-neutral-500 dark:text-neutral-400">
              {item.media_path}
            </span>
          </div>
          <div>
            <span className="font-medium">Era:</span> {eraLabel}
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

        {/* ── Edit details ── */}
        <section className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            Details
          </h2>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Title" htmlFor="detail-title" required>
              <Input
                id="detail-title"
                value={form.title}
                onChange={(e) => setField('title', e.target.value)}
                placeholder="Game or software title"
              />
            </FormField>

            <FormField label="Sort Title" htmlFor="detail-sort-title" hint="Used for alphabetical sorting (e.g. 'Doom, The')">
              <Input
                id="detail-sort-title"
                value={form.sort_title}
                onChange={(e) => setField('sort_title', e.target.value)}
                placeholder="Optional"
              />
            </FormField>
          </div>

          <FormField label="Description" htmlFor="detail-description">
            <Textarea
              id="detail-description"
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
              placeholder="Short description…"
              rows={3}
            />
          </FormField>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Publisher" htmlFor="detail-publisher">
              <Input
                id="detail-publisher"
                value={form.publisher}
                onChange={(e) => setField('publisher', e.target.value)}
                placeholder="Publisher name"
              />
            </FormField>

            <FormField label="Year" htmlFor="detail-year">
              <Input
                id="detail-year"
                type="number"
                min={1950}
                max={2099}
                value={form.year}
                onChange={(e) => setField('year', e.target.value)}
                placeholder="1993"
              />
            </FormField>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Category" htmlFor="detail-category">
              <Input
                id="detail-category"
                value={form.category}
                onChange={(e) => setField('category', e.target.value)}
                placeholder="e.g. Action, RPG"
              />
            </FormField>

            <FormField label="Content Rating" htmlFor="detail-rating">
              <select
                id="detail-rating"
                value={form.content_rating}
                onChange={(e) => setField('content_rating', e.target.value)}
                className={SELECT_CLASS}
              >
                {RATING_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </FormField>
          </div>

          <FormField label="Cover Art Path" htmlFor="detail-cover">
            <PathInput
              id="detail-cover"
              mode="file"
              accept=".png,.jpg,.jpeg,.webp"
              value={form.cover_art_path}
              onChange={(v) => setField('cover_art_path', v)}
              placeholder="C:\Images\cover.png"
            />
          </FormField>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="Era" htmlFor="detail-era">
              <select
                id="detail-era"
                value={form.era}
                onChange={(e) => setField('era', e.target.value)}
                className={SELECT_CLASS}
              >
                <option value="">— No era —</option>
                {Object.entries(ERA_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label="Platform" htmlFor="detail-platform">
              <select
                id="detail-platform"
                value={form.platform_id}
                onChange={(e) => setField('platform_id', e.target.value)}
                className={SELECT_CLASS}
              >
                <option value="">— No platform —</option>
                {platforms.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </FormField>
          </div>

          <FormField label="Launch Profile" htmlFor="detail-profile">
            <select
              id="detail-profile"
              value={form.profile_id}
              onChange={(e) => setField('profile_id', e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="">— No profile —</option>
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
            {profileEraMismatch && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                Selected profile targets a different era — launch may fail.
              </p>
            )}
          </FormField>

          <div className="flex items-center gap-3">
            <Button onClick={handleSave} loading={saving}>
              Save Changes
            </Button>
            {saveSuccess && (
              <span className="text-sm text-green-600 dark:text-green-400">Saved ✓</span>
            )}
          </div>

          {saveError && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              ❌ {saveError}
            </p>
          )}
        </section>

        {/* ── Advanced ── */}
        <section className="space-y-4">
          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wider text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
          >
            <span>Advanced</span>
            <span>{advancedOpen ? '▲' : '▼'}</span>
          </button>

          {advancedOpen && (
            <div className="space-y-5">
              {item.launch_review_flagged && (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
                  ⚠ Launch commands may be incorrect — please review.
                </div>
              )}

              <div>
                <div className="mb-1 flex items-center gap-1.5">
                  <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    Autoexec commands
                  </span>
                  <span className="group relative inline-flex cursor-help">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="h-4 w-4 text-neutral-400 dark:text-neutral-500"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <span className="pointer-events-none absolute bottom-full left-1/2 mb-1.5 w-64 -translate-x-1/2 rounded bg-neutral-800 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 dark:bg-neutral-700">
                      Commands run in sequence when the game launches, like a DOS autoexec.bat. Use CD to navigate directories, then run your executable. Example: CD DOOMCD then DOOM.EXE
                    </span>
                  </span>
                </div>
                <LaunchCommandList
                  value={launchCommands ?? []}
                  onChange={setLaunchCommands}
                />
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={rescanning}
                  onClick={handleRescan}
                >
                  Rescan
                </Button>
                {rescanError && (
                  <p role="alert" className="text-xs text-red-600 dark:text-red-400">
                    ❌ {rescanError}
                  </p>
                )}
              </div>


              <div className="flex items-center gap-3">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={flagging}
                  onClick={handleFlagLaunch}
                >
                  Flag broken launch
                </Button>
              </div>
              {flagError && (
                <p role="alert" className="text-xs text-red-600 dark:text-red-400">
                  ❌ {flagError}
                </p>
              )}
            </div>
          )}
        </section>

        {/* ── Launch ── */}
        <section className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            Launch
          </h2>

          <Button
            onClick={handleLaunch}
            loading={launching}
            disabled={!hasProfile || launching}
            className="w-full justify-center py-3 text-base"
          >
            {hasProfile ? 'Launch' : 'Assign a profile to launch'}
          </Button>

          {!hasProfile && (
            <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
              Select a launch profile above to enable launch.
            </p>
          )}

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

        {/* ── Restrictions (admin/owner only) ── */}
        {isAdminOrOwner && (
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Restrictions
            </h2>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Checked users cannot see this item in their library.
            </p>

            {nonOwnerUsers.length === 0 ? (
              <p className="text-sm text-neutral-400 dark:text-neutral-500">No sub-accounts.</p>
            ) : (
              <ul className="space-y-2">
                {nonOwnerUsers.map((user) => (
                  <li key={user.id}>
                    <label className="flex cursor-pointer items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300">
                      <input
                        type="checkbox"
                        checked={restrictedIds.has(user.id)}
                        onChange={() => toggleRestriction(user.id)}
                        className="h-4 w-4 rounded border-neutral-300 text-[#ff8a5c] focus:ring-[#ff8a5c] dark:border-neutral-600"
                      />
                      {user.name}
                    </label>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                onClick={handleSaveRestrictions}
                loading={savingRestrictions}
                disabled={!restrictionsDirty || nonOwnerUsers.length === 0}
              >
                Save Restrictions
              </Button>
            </div>

            {restrictionsError && (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                ❌ {restrictionsError}
              </p>
            )}
          </section>
        )}

        {/* ── Session history ── */}
        {launchHistory.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
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
        )}

        </div>

      </div>
    </div>
  )
}
