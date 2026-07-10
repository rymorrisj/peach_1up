import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useAppContext } from '@/context/useAppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useXisoConvert } from '@/hooks/useXisoConvert'
import { useConfirm } from '@/hooks/useConfirm'
import { useConfirmToken } from '@/hooks/useConfirmToken'
import { useCollectionRestrictions } from '@/hooks/useCollectionRestrictions'
import { SoftwareEntityDetail } from './components/SoftwareEntityDetail'
import { FetchMetadataModal } from './components/FetchMetadataModal'
import { DiscOrderList } from './components/DiscOrderList'
import { ERA_LABELS } from '@/generated/constants'
import type { SoftwareCollectionData } from './components/CollectionCard'
import type { EditForm as EditFormFields } from '@/hooks/useEditForm'
import type { components } from '@shared/types'

type User = components['schemas']['UserRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']
type LaunchProfile = components['schemas']['ProfileRead']
type Platform = components['schemas']['EnvironmentRead']

function formFromCollection(c: SoftwareCollectionData): EditFormFields {
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
    environment_id: c.environment_id?.toString() ?? '',
    profile_id: c.profile_id?.toString() ?? '',
    executable_path: launchDisc?.executable_path ?? '',
  }
}

export default function CollectionDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()

  const isAdminOrOwner =
    (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)
  const isOwner = appState.activeUser?.is_owner ?? false

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
    enabled: isOwner,
  })
  const activeProvider = (settings?.metadata_provider as string | undefined) ?? 'thegamesdb'
  const activeProviderLabel = activeProvider === 'igdb' ? 'IGDB' : 'TheGamesDB'

  const { data: theGamesDbStatus } = useQuery({
    queryKey: ['thegamesdb-api-key-status'],
    queryFn: () => apiFetch<{ enabled: boolean }>('/api/v1/settings/thegamesdb-api-key/status'),
    enabled: isOwner && activeProvider === 'thegamesdb',
    staleTime: 30_000,
  })
  const { data: igdbStatus } = useQuery({
    queryKey: ['igdb-status'],
    queryFn: () => apiFetch<{ enabled: boolean }>('/api/v1/settings/igdb-status'),
    enabled: isOwner && activeProvider === 'igdb',
    staleTime: 30_000,
  })
  const activeProviderStatus = activeProvider === 'igdb' ? igdbStatus : theGamesDbStatus
  const metadataProviderEnabled = isOwner && (activeProviderStatus?.enabled !== false)

  const [fetchMetadataOpen, setFetchMetadataOpen] = useState(false)
  const [fetchDiscId, setFetchDiscId] = useState<number | null>(null)
  const [fetchMetadataBusy, setFetchMetadataBusy] = useState(false)

  const { data: collection, isLoading } = useQuery({
    queryKey: ['library', 'by-slug', slug],
    queryFn: () => apiFetch<SoftwareCollectionData>(`/api/v1/softwarecollection/by-slug/${slug}`),
    enabled: !!slug,
  })
  const collectionId = collection?.id

  const { data: libraryDefaults } = useQuery<{ delete_media_on_removal: boolean; delete_original_on_upload: boolean }>({
    queryKey: ['settings', 'library-defaults'],
    queryFn: () => apiFetch('/api/v1/settings/library-defaults'),
    staleTime: 60_000,
  })
  const deleteMediaOnRemoval = Boolean(libraryDefaults?.delete_media_on_removal)

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
      apiFetch<{ restricted_user_ids: number[] }>(`/api/v1/softwarecollection/${collectionId}/restrictions`),
    enabled: isAdminOrOwner && collectionId != null,
  })

  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', 'collection', collectionId],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/softwarecollection/${collectionId}/launches`),
    enabled: collectionId != null,
  })

  const [form, setFormState] = useState<EditFormFields | null>(null)
  const [execBrowserOpen, setExecBrowserOpen] = useState(false)
  // Staged disc order (leaf ids, top-to-bottom) from <DiscOrderList>. null =
  // no local edit yet — derive display order from the collection's current
  // disc_number. Persisted only on Save, never written live on drag/move.
  const [discOrder, setDiscOrder] = useState<number[] | null>(null)
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

  // Reordering discs changes which leaf is the (staged) launch target — resync
  // the Launch File field to that disc's own executable_path so it never shows
  // a stale value from whichever disc used to be on top. Each disc's
  // executable_path is already its own file by construction (see items.py's
  // _create_multi_disc_collection), so this always reflects a correct default;
  // the user can still override via Browse after reordering.
  useEffect(() => {
    if (!collection || discOrder == null) return
    const newLaunchDisc = collection.items.find((i) => i.id === discOrder[0])
    setFormState((prev) => prev && { ...prev, executable_path: newLaunchDisc?.executable_path ?? '' })
    // Only re-run when the staged top disc actually changes, not on every
    // keystroke elsewhere in the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [discOrder?.[0]])

  // Send state verbatim so [] (cleared) and null (unset) are preserved. null is
  // dropped server-side (exclude_none), leaving the stored value untouched — so
  // an incidental save without touching commands can't flip null → [].
  function resolveLaunchCommands(): string[] | null {
    return launchCommands === undefined ? (collection?.launch_commands ?? null) : launchCommands
  }

  const saveMutation = useMutation<SoftwareCollectionData, Error, EditFormFields>({
    mutationFn: async (f) => {
      await apiFetch<SoftwareCollectionData>(`/api/v1/softwarecollection/${collectionId}`, {
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
          environment_id: f.environment_id ? parseInt(f.environment_id, 10) : null,
          profile_id: f.profile_id ? parseInt(f.profile_id, 10) : null,
          launch_commands: resolveLaunchCommands(),
        }),
      })

      // Persist a staged reorder (if any) before deciding which disc gets the
      // executable_path edit below — otherwise an edit made after reordering
      // would land on the disc that *was* the launch disc before this save,
      // not the one the user just dragged to the top.
      const currentOrderIds = (collection?.items ?? [])
        .slice()
        .sort((a, b) => a.disc_number - b.disc_number)
        .map((i) => i.id)
      const reorderStaged =
        discOrder != null &&
        (discOrder.length !== currentOrderIds.length || discOrder.some((id, i) => id !== currentOrderIds[i]))
      if (reorderStaged && collectionId != null) {
        await apiFetch(`/api/v1/softwarecollection/${collectionId}/items/reorder`, {
          method: 'PATCH',
          body: JSON.stringify({ disc_order: discOrder }),
        })
      }

      const launchDiscId = reorderStaged
        ? discOrder![0]
        : (collection?.launch_disk_id ?? collection?.items[0]?.id)
      if (launchDiscId != null && collectionId != null) {
        await apiFetch(`/api/v1/softwarecollection/${collectionId}/items/${launchDiscId}`, {
          method: 'PATCH',
          body: JSON.stringify({ executable_path: f.executable_path.trim() || null }),
        })
      }

      // Fetch fresh, fully up-to-date collection data (reflecting the collection
      // fields, disc order, and launch-disc executable_path changes above) so
      // the form can resync deterministically in onSuccess rather than relying
      // on invalidateQueries' background refetch timing.
      return apiFetch<SoftwareCollectionData>(`/api/v1/softwarecollection/by-slug/${slug}`)
    },
    onSuccess: (fresh) => {
      setDiscOrder(null)
      setFormState(formFromCollection(fresh))
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
      return apiFetch(`/api/v1/softwarecollection/${collectionId}`, {
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

  // Persistent per-collection override for delete_media_on_removal — checking
  // or unchecking PATCHes immediately, no staging behind Save Changes.
  const deleteMediaOverrideMutation = useMutation<void, Error, boolean>({
    mutationFn: (value) => {
      if (collectionId == null) return Promise.resolve()
      return apiFetch(`/api/v1/softwarecollection/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ delete_media_override: value }),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
      // Also invalidate the grid/list query — its own delete-confirm modal seeds
      // its checkbox from this same collection's delete_media_override, and
      // without this it can read stale data if the user navigates back there
      // shortly after toggling the item-level checkbox here.
      queryClient.invalidateQueries({ queryKey: ['library'] })
    },
  })

  const {
    confirm: confirmDelete,
    isOpen: deleteConfirmOpen,
    options: deleteConfirmOptions,
    handleConfirm: handleDeleteConfirm,
    handleCancel: handleDeleteCancel,
    getCheckboxValue: getDeleteCheckboxValue,
  } = useConfirm()
  const { issue: issueDeleteToken, consume: consumeDeleteToken } = useConfirmToken()
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function handleDelete() {
    if (collectionId == null || !collection) return
    const resolvedDeleteMedia = collection.delete_media_override ?? deleteMediaOnRemoval
    const confirmed = await confirmDelete({
      title: `Delete "${collection.title}"?`,
      consequence: 'This removes the game from your library.',
      destructive: true,
      checkbox: { label: 'Also delete media files from disk', defaultChecked: resolvedDeleteMedia },
    })
    if (!confirmed) return
    setDeleting(true)
    setDeleteError(null)
    try {
      const checkedDeleteMedia = getDeleteCheckboxValue()
      // Always persist the confirm-dialog's checkbox value explicitly before
      // deleting — never skip this based on a comparison against
      // resolvedDeleteMedia (React Query cache), which can still be stale if
      // the standalone override checkbox above (deleteMediaOverrideMutation,
      // fire-and-forget) was toggled moments earlier and hasn't round-tripped
      // yet. Writing unconditionally makes this the single source of truth
      // delete_library_collection reads, regardless of cache freshness.
      await apiFetch(`/api/v1/softwarecollection/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ delete_media_override: checkedDeleteMedia }),
      })
      const token = await issueDeleteToken(`/api/v1/softwarecollection/${collectionId}/confirm-delete`)
      await consumeDeleteToken(`/api/v1/softwarecollection/${collectionId}`, token)
      queryClient.invalidateQueries({ queryKey: ['library'] })
      navigate('/software')
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.detail : 'Delete failed.')
      setDeleting(false)
    }
  }

  const [flagging, setFlagging] = useState(false)
  const [flagError, setFlagError] = useState<string | null>(null)

  async function handleFlagLaunch() {
    if (collectionId == null) return
    setFlagging(true)
    setFlagError(null)
    try {
      await apiFetch(`/api/v1/softwarecollection/${collectionId}/flag-launch`, { method: 'POST' })
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
      await apiFetch(`/api/v1/tags/${tagId}/assignments`, {
        method: 'DELETE',
        body: JSON.stringify({ entity_type: 'software_collection', entity_id: collectionId }),
      })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to remove tag.')
    }
  }

  async function handleAssignTag(tagId: number) {
    if (collectionId == null) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ entity_type: 'software_collection', entity_id: collectionId }),
      })
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

  const {
    launch, isLaunching, error: launchError, errorType: launchErrorType, launchSuccess, launchWarnings,
  } = useLaunch({
    targetId: collectionId ?? 0,
    targetType: 'collection',
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
      queryClient.invalidateQueries({ queryKey: ['launches', 'collection', collectionId] })
    },
  })
  const xisoConvert = useXisoConvert(collectionId ?? 0)

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
        <Link to="/software" className="text-sm text-[#ff8a5c] hover:underline">
          ← Back to Software
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

  // Staged order takes precedence over the server's disc_number order once
  // the user has dragged/moved a disc, so the "Launch File" field below and
  // the "Launch target" badge in the disc list both reflect the not-yet-saved
  // choice consistently.
  const displayedOrder = discOrder ?? sortedItems.map((i) => i.id)
  const currentLaunchDisc =
    sortedItems.find((i) => i.id === displayedOrder[0]) ?? sortedItems[0]

  const effectiveProfileId = form.profile_id
    ? parseInt(form.profile_id, 10)
    : (collection.profile_id ?? null)
  const hasProfile = effectiveProfileId != null

  const resolvedDeleteMedia = collection.delete_media_override ?? deleteMediaOnRemoval

  function setFormField<K extends keyof EditFormFields>(key: K, value: EditFormFields[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  const storageKey = `fetch_metadata_${window.location.pathname}`
  const activeDisc = fetchDiscId != null ? sortedItems.find((d) => d.id === fetchDiscId) : undefined

  return (
    <>
    <SoftwareEntityDetail
      title={collection.title}
      eraLabel={eraLabel}
      launchCount={collection.launch_count}
      lastLaunchedAt={collection.last_launched_at}
      topControl={
        <section className="space-y-3 rounded-md border border-neutral-200 bg-neutral-50 px-4 py-3 dark:border-surface-700 dark:bg-surface-900">
          <label
            htmlFor="delete-media-override"
            className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300"
          >
            <input
              type="checkbox"
              id="delete-media-override"
              checked={resolvedDeleteMedia}
              onChange={(e) => deleteMediaOverrideMutation.mutate(e.target.checked)}
              className="h-4 w-4"
            />
            Delete all files/folders when you delete this in Peach 1UP?
          </label>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            loading={deleting}
          >
            Delete this collection
          </Button>
          {deleteError && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">{deleteError}</p>
          )}
        </section>
      }
      metaAfter={
        <>
          {isMultiDisc && (
            <div>
              <span className="font-medium">Discs:</span> {collection.items.length}
            </div>
          )}
          {collection.genres.length > 0 && (
            <div>
              <span className="font-medium">Genre:</span> {collection.genres.join(', ')}
            </div>
          )}
          {collection.developer && (
            <div>
              <span className="font-medium">Developer:</span> {collection.developer}
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
          media_path: currentLaunchDisc?.media_path,
          folder_path: currentLaunchDisc?.folder_path,
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
                disabled={!metadataProviderEnabled || fetchMetadataBusy}
                loading={fetchMetadataBusy}
                title={!metadataProviderEnabled ? `${activeProviderLabel} credentials not configured — set them in Settings > Advanced` : undefined}
              >
                Fetch Metadata
              </Button>
              {!isMultiDisc && sortedItems[0] && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setFetchDiscId(sortedItems[0].id)}
                  disabled={!metadataProviderEnabled || fetchMetadataBusy}
                  loading={fetchMetadataBusy && fetchDiscId === sortedItems[0].id}
                  title={!metadataProviderEnabled ? `${activeProviderLabel} credentials not configured` : 'Fetch cover art for this disc'}
                >
                  Cover Art
                </Button>
              )}
              {!metadataProviderEnabled && (
                <span className="text-xs text-neutral-400">
                  Requires {activeProviderLabel} credentials (Settings &gt; Advanced)
                </span>
              )}
            </div>
          </section>
        ) : null
      }
      beforeLaunch={
        <>
          {/* Disc list is shown only for multi-disc collections. Drag (or use
              the up/down buttons) to reorder — staged locally, persisted only
              when "Save Changes" above is pressed. */}
          {isMultiDisc && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                Discs
              </h2>
              <DiscOrderList
                discs={sortedItems}
                order={displayedOrder}
                onReorder={setDiscOrder}
                disabled={saveMutation.isPending}
                renderActions={(disc) =>
                  isOwner ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setFetchDiscId(disc.id)}
                      disabled={!metadataProviderEnabled || fetchMetadataBusy}
                      loading={fetchMetadataBusy && fetchDiscId === disc.id}
                      title={!metadataProviderEnabled ? `${activeProviderLabel} credentials not configured` : 'Fetch cover art for this disc'}
                      className="shrink-0"
                    >
                      Cover Art
                    </Button>
                  ) : null
                }
              />
              {discOrder != null && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Disc order changed — press "Save Changes" above to persist it.
                </p>
              )}
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
      launchErrorAction={
        launchErrorType === 'xbox_dvd_rip' ? (
          <div className="mt-2 space-y-1 text-center">
            {xisoConvert.status === 'complete' ? (
              <p className="text-xs text-green-600 dark:text-green-400">
                Conversion complete. Click Launch to try again. The original rip was kept as{' '}
                {'<filename>.old'} in the same folder — delete it manually to free up disk space.
              </p>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                onClick={xisoConvert.convert}
                loading={xisoConvert.isConverting}
              >
                {xisoConvert.isConverting
                  ? 'Converting… this can take a while for large images'
                  : 'Convert with extract-xiso'}
              </Button>
            )}
            {xisoConvert.error && (
              <p className="text-xs text-red-600 dark:text-red-400">{xisoConvert.error}</p>
            )}
          </div>
        ) : undefined
      }
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
      currentContentRating={collection.content_rating}
      storageKey={storageKey}
      activeProviderLabel={activeProviderLabel}
      onSuccess={async () => {
        queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
        queryClient.invalidateQueries({ queryKey: ['library'] })
        // Fetch fresh data directly and resync the edit form — the form is only
        // built from `collection` once (see the `!form` guard above), so it
        // would otherwise show stale publisher/description/category/rating/
        // cover art fields until a full page reload even after the invalidated
        // query refetches in the background.
        const fresh = await apiFetch<SoftwareCollectionData>(`/api/v1/softwarecollection/by-slug/${slug}`)
        setFormState(formFromCollection(fresh))
      }}
      onBusyChange={setFetchMetadataBusy}
    />

    {fetchDiscId != null && activeDisc != null && (
      <FetchMetadataModal
        open={fetchDiscId != null}
        onClose={() => setFetchDiscId(null)}
        entityType="library_item"
        entityId={fetchDiscId}
        entityTitle={activeDisc.media_path.split(/[\\/]/).pop() ?? collection.title}
        storageKey={`${storageKey}#disc-${fetchDiscId}`}
        activeProviderLabel={activeProviderLabel}
        onSuccess={async () => {
          queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
          queryClient.invalidateQueries({ queryKey: ['library'] })
          const fresh = await apiFetch<SoftwareCollectionData>(`/api/v1/softwarecollection/by-slug/${slug}`)
          setFormState(formFromCollection(fresh))
          setFetchDiscId(null)
        }}
        onBusyChange={setFetchMetadataBusy}
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

    <ConfirmModal
      open={deleteConfirmOpen}
      title={deleteConfirmOptions?.title ?? ''}
      consequence={deleteConfirmOptions?.consequence ?? ''}
      destructive={deleteConfirmOptions?.destructive}
      checkbox={deleteConfirmOptions?.checkbox}
      onConfirm={handleDeleteConfirm}
      onCancel={handleDeleteCancel}
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
