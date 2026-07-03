import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useAppContext } from '@/context/useAppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useConfirm } from '@/hooks/useConfirm'
import { useCollectionRestrictions } from '@/hooks/useCollectionRestrictions'
import { LibraryEntityDetail } from './components/LibraryEntityDetail'
import { FetchMetadataModal } from './components/FetchMetadataModal'
import { ERA_LABELS } from '@/generated/constants'
import type { LibraryCollectionData } from './components/CollectionCard'
import type { EditForm as EditFormFields } from '@/hooks/useEditForm'
import type { components } from '@shared/types'

type User = components['schemas']['UserRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']
type LaunchProfile = components['schemas']['ProfileRead']
type Platform = components['schemas']['PlatformRead']

function formFromCollection(c: LibraryCollectionData): EditFormFields {
  const launchDisc = c.items.find(i => i.id === c.launch_disk_id) ?? c.items[0]
  return {
    title: c.title,
    sort_title: c.sort_title ?? '',
    description: c.description ?? '',
    publisher: c.publisher ?? '',
    year: c.year?.toString() ?? '',
    category: c.category ?? '',
    cover_art_path: '',
    content_rating: c.content_rating ?? '',
    era: c.era && c.era !== 'unknown' ? c.era : '',
    platform_id: c.platform_id?.toString() ?? '',
    profile_id: c.profile_id?.toString() ?? '',
    executable_path: launchDisc?.executable_path ?? '',
  }
}

export default function CollectionDetail() {
  const { slug } = useParams<{ slug: string }>()
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()

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

  const { data: collection, isLoading } = useQuery({
    queryKey: ['library', 'by-slug', slug],
    queryFn: () => apiFetch<LibraryCollectionData>(`/api/v1/librarycollection/by-slug/${slug}`),
    enabled: !!slug,
  })
  const collectionId = collection?.id

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
    queryKey: ['restrictions', 'collection', collectionId],
    queryFn: () =>
      apiFetch<{ restricted_user_ids: number[] }>(`/api/v1/librarycollection/${collectionId}/restrictions`),
    enabled: isAdminOrOwner && collectionId != null,
  })

  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', 'collection', collectionId],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/library/${collectionId}/launches`),
    enabled: collectionId != null,
  })

  const [form, setFormState] = useState<EditFormFields | null>(null)
  const [execBrowserOpen, setExecBrowserOpen] = useState(false)
  // undefined = not yet loaded; null = never configured (preserve, media may
  // auto-run); [] = explicitly cleared (persist as empty → no auto-run).
  // Using undefined as the load sentinel keeps null distinguishable from [].
  const [launchCommands, setLaunchCommandsState] = useState<string[] | null | undefined>(undefined)
  const [localInstalled, setLocalInstalled] = useState(false)

  useEffect(() => {
    if (collection && !form) {
      setFormState(formFromCollection(collection))
      setLaunchCommandsState(collection.launch_commands ?? null)
      setLocalInstalled(collection.installed)
    }
  }, [collection, form])

  // Send state verbatim so [] (cleared) and null (unset) are preserved. null is
  // dropped server-side (exclude_none), leaving the stored value untouched — so
  // an incidental save without touching commands can't flip null → [].
  function resolveLaunchCommands(): string[] | null {
    return launchCommands === undefined ? (collection?.launch_commands ?? null) : launchCommands
  }

  const saveMutation = useMutation<LibraryCollectionData, Error, EditFormFields>({
    mutationFn: async (f) => {
      const result = await apiFetch<LibraryCollectionData>(`/api/v1/librarycollection/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: f.title.trim() || undefined,
          sort_title: f.sort_title.trim() || null,
          description: f.description.trim() || null,
          publisher: f.publisher.trim() || null,
          year: f.year ? parseInt(f.year, 10) : null,
          category: f.category.trim() || null,
          content_rating: f.content_rating || null,
          era: f.era || null,
          platform_id: f.platform_id ? parseInt(f.platform_id, 10) : null,
          profile_id: f.profile_id ? parseInt(f.profile_id, 10) : null,
          launch_commands: resolveLaunchCommands(),
        }),
      })
      const disc = collection?.items.find(i => i.id === collection.launch_disk_id) ?? collection?.items[0]
      if (disc && collectionId != null) {
        await apiFetch(`/api/v1/librarycollection/${collectionId}/items/${disc.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ executable_path: f.executable_path.trim() || null }),
        })
      }
      return result
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    },
  })

  const {
    confirm: confirmInstalled,
    isOpen: installedConfirmOpen,
    options: installedConfirmOptions,
    handleConfirm: handleInstalledConfirm,
    handleCancel: handleInstalledCancel,
  } = useConfirm()

  const installedMutation = useMutation<void, Error, boolean>({
    mutationFn: (value) => {
      if (collectionId == null) return Promise.resolve()
      return apiFetch(`/api/v1/librarycollection/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ installed: value }),
      })
    },
    onSuccess: (_, value) => {
      setLocalInstalled(value)
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    },
  })

  async function handleToggleInstalled() {
    if (collectionId == null) return
    const target = !localInstalled
    const consequence = target
      ? 'Only confirm if your game files are already copied to this drive. Peach 1UP will skip the copy step and boot directly.'
      : 'This will re-run the copy step on next launch. Any changes made inside the drive will be preserved but source files will be copied again.'
    const confirmed = await confirmInstalled({
      title: target ? 'Mark as installed?' : 'Mark as not installed?',
      consequence,
      destructive: !target,
    })
    if (confirmed) installedMutation.mutate(target)
  }

  const [flagging, setFlagging] = useState(false)
  const [flagError, setFlagError] = useState<string | null>(null)

  async function handleFlagLaunch() {
    if (collectionId == null) return
    setFlagging(true)
    setFlagError(null)
    try {
      await apiFetch(`/api/v1/librarycollection/${collectionId}/flag-launch`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setFlagError(err instanceof ApiError ? err.detail : 'Failed to flag.')
    } finally {
      setFlagging(false)
    }
  }

  const [tagError, setTagError] = useState<string | null>(null)

  async function handleRemoveTag(tagId: number) {
    if (collectionId == null) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/collections/${collectionId}`, { method: 'DELETE' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to remove tag.')
    }
  }

  async function handleAssignTag(tagId: number) {
    if (collectionId == null) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/collections/${collectionId}`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to add tag.')
    }
  }

  const restrictions = useCollectionRestrictions({
    collectionId,
    isAdminOrOwner,
    restrictionsData,
    refetchRestrictions,
  })

  const { launch, isLaunching, error: launchError, launchSuccess, launchWarnings } = useLaunch({
    targetId: collectionId ?? 0,
    targetType: 'collection',
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
      queryClient.invalidateQueries({ queryKey: ['launches', 'collection', collectionId] })
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

  if (!collection || !form) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-neutral-500">Game not found.</p>
        <Link to="/library" className="text-sm text-[#ff8a5c] hover:underline">
          ← Back to Library
        </Link>
      </div>
    )
  }

  const eraLabel = ERA_LABELS[collection.era] ?? (collection.era === 'unknown' ? 'Unknown' : collection.era)
  const sortedItems = collection.items.slice().sort((a, b) => a.disc_number - b.disc_number)
  // Single-disc games are collections-of-one — suppress the disc list entirely.
  const isMultiDisc = sortedItems.length > 1
  const showDiscSwapWarning = (collection.era === 'ps1' || collection.era === 'ps2') && isMultiDisc
  const nonOwnerUsers = users.filter((u) => !u.is_owner)

  const effectiveProfileId = form.profile_id
    ? parseInt(form.profile_id, 10)
    : (collection.profile_id ?? null)
  const hasProfile = effectiveProfileId != null

  function setFormField<K extends keyof EditFormFields>(key: K, value: EditFormFields[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  const storageKey = `fetch_metadata_${window.location.pathname}`
  const activeDisc = fetchDiscId != null ? sortedItems.find((d) => d.id === fetchDiscId) : undefined

  return (
    <>
    <LibraryEntityDetail
      title={collection.title}
      eraLabel={eraLabel}
      launchCount={collection.launch_count}
      lastLaunchedAt={collection.last_launched_at}
      metaAfter={
        <>
          {isMultiDisc && (
            <div>
              <span className="font-medium">Discs:</span> {collection.items.length}
            </div>
          )}
          {collection.era === 'dos' && (
            <div className="flex items-center gap-2">
              <span className="font-medium shrink-0">Installed:</span>
              <span className="text-neutral-500 dark:text-neutral-400">
                {localInstalled ? '● Yes' : '○ No'}
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleToggleInstalled}
                loading={installedMutation.isPending}
              >
                {localInstalled ? 'Mark as not installed' : 'Mark as installed'}
              </Button>
            </div>
          )}
        </>
      }
      tags={
        isAdminOrOwner || collection.tags.length > 0
          ? {
              entity: { id: collection.id, tags: collection.tags },
              isAdminOrOwner,
              onRemove: handleRemoveTag,
              onAssign: handleAssignTag,
              error: tagError,
            }
          : undefined
      }
      editForm={{
        item: {
          era: form.era || collection.era,
          media_path: (collection.items.find(i => i.id === collection.launch_disk_id) ?? collection.items[0])?.media_path,
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
      advancedSection={{
        item: { launch_review_flagged: collection.launch_review_flagged },
        flagging,
        flagError,
        onFlagLaunch: handleFlagLaunch,
        launchCommands: launchCommands ?? null,
        setLaunchCommands: setLaunchCommandsState,
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
          {/* Disc list is shown only for multi-disc collections. */}
          {isMultiDisc && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                Discs
              </h2>
              <ul className="space-y-1.5">
                {sortedItems.map((disc) => {
                  const isLaunch = disc.id === collection.launch_disk_id
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
          )}

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
      entityType="library_collection"
      entityId={collection.id}
      entityTitle={collection.title}
      storageKey={storageKey}
      onSuccess={() => {
        queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
        queryClient.invalidateQueries({ queryKey: ['library'] })
      }}
    />

    {fetchDiscId != null && activeDisc != null && (
      <FetchMetadataModal
        open={fetchDiscId != null}
        onClose={() => setFetchDiscId(null)}
        entityType="library_item"
        entityId={fetchDiscId}
        entityTitle={activeDisc.media_path.split(/[\\/]/).pop() ?? collection.title}
        storageKey={`${storageKey}#disc-${fetchDiscId}`}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
          queryClient.invalidateQueries({ queryKey: ['library'] })
          setFetchDiscId(null)
        }}
      />
    )}

    <ConfirmModal
      open={installedConfirmOpen}
      title={installedConfirmOptions?.title ?? ''}
      consequence={installedConfirmOptions?.consequence ?? ''}
      destructive={installedConfirmOptions?.destructive}
      onConfirm={handleInstalledConfirm}
      onCancel={handleInstalledCancel}
    />

    {installedMutation.isError && (
      <p role="alert" className="sr-only">
        {installedMutation.error instanceof ApiError
          ? installedMutation.error.detail
          : 'Failed to update.'}
      </p>
    )}
    </>
  )
}
