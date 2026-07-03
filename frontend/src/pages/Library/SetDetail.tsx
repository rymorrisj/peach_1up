import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useAppContext } from '@/context/useAppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useSetRestrictions } from '@/hooks/useSetRestrictions'
import { LibraryEntityDetail } from './components/LibraryEntityDetail'
import { FetchMetadataModal } from './components/FetchMetadataModal'
import { ERA_LABELS } from '@/generated/constants'
import type { LibrarySetData } from './components/SetCard'
import type { EditForm as EditFormFields } from '@/hooks/useEditForm'
import type { components } from '@shared/types'

type User = components['schemas']['UserRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']
type LaunchProfile = components['schemas']['ProfileRead']
type Platform = components['schemas']['PlatformRead']

function formFromSet(set: LibrarySetData): EditFormFields {
  const launchDisc = set.items.find(i => i.id === set.launch_disk_id) ?? set.items[0]
  return {
    title: set.title,
    sort_title: set.sort_title ?? '',
    description: set.description ?? '',
    publisher: set.publisher ?? '',
    year: set.year?.toString() ?? '',
    category: set.category ?? '',
    cover_art_path: '',
    content_rating: set.content_rating ?? '',
    era: set.era && set.era !== 'unknown' ? set.era : '',
    platform_id: set.platform_id?.toString() ?? '',
    profile_id: set.profile_id?.toString() ?? '',
    executable_path: launchDisc?.executable_path ?? '',
  }
}

export default function SetDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()
  const setId = Number(id)

  const isAdminOrOwner =
    (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)
  const isOwner = appState.activeUser?.is_owner ?? false

  const { data: apiKeyStatus } = useQuery({
    queryKey: ['thegamesdb-api-key-status'],
    queryFn: () => apiFetch<{ enabled: boolean }>('/api/v1/settings/thegamesdb-api-key/status'),
    enabled: isOwner,
    staleTime: 30_000,
  })
  const theGamesDbEnabled = isOwner && (apiKeyStatus?.enabled !== false)

  const [fetchMetadataOpen, setFetchMetadataOpen] = useState(false)
  const [fetchDiscId, setFetchDiscId] = useState<number | null>(null)

  const { data: set, isLoading } = useQuery({
    queryKey: ['library', 'sets', setId],
    queryFn: () => apiFetch<LibrarySetData>(`/api/v1/library/sets/${setId}`),
    enabled: !isNaN(setId),
  })

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/users'),
    enabled: isAdminOrOwner,
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: platforms = [] } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const { data: restrictionsData, refetch: refetchRestrictions } = useQuery<{
    restricted_user_ids: number[]
  }>({
    queryKey: ['restrictions', 'set', setId],
    queryFn: () =>
      apiFetch<{ restricted_user_ids: number[] }>(`/api/v1/library/sets/${setId}/restrictions`),
    enabled: isAdminOrOwner && !isNaN(setId),
  })

  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', 'set', setId],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/library/sets/${setId}/launches`),
    enabled: !isNaN(setId),
  })

  const [form, setFormState] = useState<EditFormFields | null>(null)
  const [execBrowserOpen, setExecBrowserOpen] = useState(false)

  useEffect(() => {
    if (set && !form) setFormState(formFromSet(set))
  }, [set, form])

  const saveMutation = useMutation<LibrarySetData, Error, EditFormFields>({
    mutationFn: async (f) => {
      const result = await apiFetch<LibrarySetData>(`/api/v1/library/sets/${setId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: f.title.trim() || undefined,
          sort_title: f.sort_title.trim() || null,
          description: f.description.trim() || null,
          publisher: f.publisher.trim() || null,
          year: f.year ? parseInt(f.year, 10) : null,
          category: f.category.trim() || null,
          cover_art_path: f.cover_art_path.trim() || undefined,
          content_rating: f.content_rating || null,
          era: f.era || null,
          platform_id: f.platform_id ? parseInt(f.platform_id, 10) : null,
          profile_id: f.profile_id ? parseInt(f.profile_id, 10) : null,
        }),
      })
      const disc = set?.items.find(i => i.id === set.launch_disk_id) ?? set?.items[0]
      if (disc) {
        await apiFetch(`/api/v1/library/sets/${setId}/items/${disc.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ executable_path: f.executable_path.trim() || null }),
        })
      }
      return result
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
    },
  })

  const [tagError, setTagError] = useState<string | null>(null)

  async function handleRemoveTag(tagId: number) {
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/sets/${setId}`, { method: 'DELETE' })
      queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to remove tag.')
    }
  }

  async function handleAssignTag(tagId: number) {
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/sets/${setId}`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to add tag.')
    }
  }

  const restrictions = useSetRestrictions({
    setId: isNaN(setId) ? undefined : setId,
    isAdminOrOwner,
    restrictionsData,
    refetchRestrictions,
  })

  const { launch, isLaunching, error: launchError, launchSuccess, launchWarnings } = useLaunch({
    targetId: setId,
    targetType: 'set',
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
      queryClient.invalidateQueries({ queryKey: ['launches', 'set', setId] })
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

  if (!set || !form) {
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
  const showDiscSwapWarning = (set.era === 'ps1' || set.era === 'ps2') && sortedItems.length > 1
  const nonOwnerUsers = users.filter((u) => !u.is_owner)

  const effectiveProfileId = form.profile_id
    ? parseInt(form.profile_id, 10)
    : (set.profile_id ?? null)
  const hasProfile = effectiveProfileId != null

  function setFormField<K extends keyof EditFormFields>(key: K, value: EditFormFields[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  const setStorageKey = `fetch_metadata_${window.location.pathname}`
  const activeDisc = fetchDiscId != null ? sortedItems.find((d) => d.id === fetchDiscId) : undefined

  return (
    <>
    <LibraryEntityDetail
      title={set.title}
      eraLabel={eraLabel}
      launchCount={set.launch_count}
      lastLaunchedAt={set.last_launched_at}
      metaAfter={
        <div>
          <span className="font-medium">Discs:</span> {set.items.length}
        </div>
      }
      tags={
        isAdminOrOwner || set.tags.length > 0
          ? {
              entity: { id: set.id, tags: set.tags },
              isAdminOrOwner,
              onRemove: handleRemoveTag,
              onAssign: handleAssignTag,
              error: tagError,
            }
          : undefined
      }
      editForm={{
        item: {
          era: form.era || set.era,
          media_path: (set.items.find(i => i.id === set.launch_disk_id) ?? set.items[0])?.media_path,
        },
        form,
        setField: setFormField,
        handleSave: () => saveMutation.mutate(form),
        saving: saveMutation.isPending,
        saveError: saveMutation.isError
          ? (saveMutation.error instanceof ApiError ? saveMutation.error.detail : 'Failed to save.')
          : null,
        saveSuccess: saveMutation.isSuccess,
        execBrowserOpen,
        setExecBrowserOpen,
        profiles,
        platforms,
      }}
      fetchMetadataAction={
        isOwner ? (
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Metadata
            </h2>
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setFetchMetadataOpen(true)}
                disabled={!theGamesDbEnabled}
                title={!theGamesDbEnabled ? 'TheGamesDB API key not configured — set it in Settings > Metadata' : undefined}
              >
                Fetch Metadata
              </Button>
              {!theGamesDbEnabled && (
                <span className="text-xs text-neutral-400">
                  Requires a TheGamesDB API key (Settings &gt; Metadata)
                </span>
              )}
            </div>
          </section>
        ) : null
      }
      beforeLaunch={
        <>
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
                    {isOwner && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFetchDiscId(disc.id)}
                        disabled={!theGamesDbEnabled}
                        title={!theGamesDbEnabled ? 'TheGamesDB API key not configured' : 'Fetch cover art for this disc'}
                        className="shrink-0"
                      >
                        Cover Art
                      </Button>
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
        </>
      }
      onLaunch={() => { if (effectiveProfileId != null) launch(effectiveProfileId) }}
      launching={isLaunching}
      launchDisabled={!hasProfile || isLaunching}
      launchButtonLabel={hasProfile ? 'Launch' : 'Assign a profile to launch'}
      launchNote={
        !hasProfile ? (
          <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
            Select a launch profile above to enable launch.
          </p>
        ) : undefined
      }
      launchSuccess={launchSuccess}
      launchWarnings={launchWarnings}
      launchError={launchError}
      restrictions={
        isAdminOrOwner
          ? {
              users: nonOwnerUsers,
              restrictedIds: restrictions.restrictedIds,
              restrictionsDirty: restrictions.restrictionsDirty,
              toggleRestriction: restrictions.toggleRestriction,
              onSave: restrictions.handleSaveRestrictions,
              saving: restrictions.savingRestrictions,
              error: restrictions.restrictionsError,
            }
          : undefined
      }
      launchHistory={launchHistory}
    />

    <FetchMetadataModal
      open={fetchMetadataOpen}
      onClose={() => setFetchMetadataOpen(false)}
      entityType="library_set"
      entityId={setId}
      entityTitle={set.title}
      storageKey={setStorageKey}
      onSuccess={() => {
        queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
        queryClient.invalidateQueries({ queryKey: ['library-sets'] })
      }}
    />

    {fetchDiscId != null && activeDisc != null && (
      <FetchMetadataModal
        open={fetchDiscId != null}
        onClose={() => setFetchDiscId(null)}
        entityType="library_set_item"
        entityId={fetchDiscId}
        entityTitle={activeDisc.media_path.split(/[\\/]/).pop() ?? set.title}
        storageKey={`${setStorageKey}#disc-${fetchDiscId}`}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['library', 'sets', setId] })
          queryClient.invalidateQueries({ queryKey: ['library-sets'] })
          setFetchDiscId(null)
        }}
      />
    )}
    </>
  )
}
