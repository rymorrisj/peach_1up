import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useXisoConvert } from '@/hooks/useXisoConvert'
import { useDiscOrder } from '@/hooks/useDiscOrder'
import { useInstalledToggle } from '@/hooks/useInstalledToggle'
import { useFlagLaunch } from '@/hooks/useFlagLaunch'
import { useDeleteCollection } from '@/hooks/useDeleteCollection'
import { useEditForm } from '@/hooks/useEditForm'
import { formFromCollection, type SoftwareGameForm as EditFormFields } from '../types/gameForm'
import { resolveLaunchCommands } from '@/hooks/resolveLaunchCommands'
import { FetchMetadataModal } from '../components/FetchMetadataModal'
import { DiscOrderList } from '../components/DiscOrderList'
import { CollectionCard, getGameCoverArt } from '../components/CollectionCard'
import type { GameItemBundleData } from '../components/CollectionCard'
import { LinkedItemsSection } from '../components/LinkedItemsSection'
import { ERA_LABELS } from '@/generated/constants'
import type { EntityDetailExtras, EntityDetailExtrasContext, EntityDomainConfig } from '../types'
import { launchGateFromReason, SOFTWARE_SORT_OPTIONS, GAME_ROUTE_BASE } from '../types'
import type { LibraryModalConfig } from '../components/LibraryModal'
import type { components } from '@shared/types'

type LaunchHistory = components['schemas']['LaunchHistoryRead']
type LaunchProfile = components['schemas']['ProfileItemRead']
type Platform = components['schemas']['EnvironmentItemRead']

// Game's detail route/fetch is keyed by slug (no numeric-id lookup endpoint
// on the backend), so bundleApiPath here means "by-slug", not "by-id".
function gameBundleApiPath(slug: string): string {
  return `/api/v1/game-item-bundle/by-slug/${slug}`
}

function formIsReady<T>(form: T | null): form is T {
  return form != null
}

// Fires only when opening/triggering a Fetch Metadata search (a real call to
// the provider, costing API credits/allowance) for an item that already has
// metadata_fetched_at set. Accept All never calls this: it only reuses
// state a search already fetched into the modal, it never calls the
// provider again, so it needs no warning of its own.
function confirmRefetchIfAlreadyFetched(metadataFetchedAt: string | null | undefined): boolean {
  if (!metadataFetchedAt) return true
  return window.confirm(
    'Metadata was already fetched for this item. Fetching again will use additional ' +
      'API credits/allowance. Continue?',
  )
}

// Composes every game-only concern (disc reorder, DOS-install, xiso convert,
// edit form, launch_commands, flag launch, delete flow, metadata enrich) into
// the slot shape EntityDetailPage renders. Called unconditionally on every
// render of EntityDetailPage when mounted with gameDomainConfig — every hook
// below must tolerate `collection`/`collectionId` being undefined (pre-load),
// exactly like CollectionDetail.tsx's pre-composition body did.
function useGameDetailExtras(ctx: EntityDetailExtrasContext<GameItemBundleData>): EntityDetailExtras {
  const collection = ctx.entity
  const collectionId = ctx.entityId
  const { detailQueryKey, isOwner, launch, isLaunching, launchErrorType, refetchEntity } = ctx
  const navigate = useNavigate()
  const queryClient = useQueryClient()

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
  // Two independent instances of <FetchMetadataModal> mount below (one for
  // the whole collection, one per-disc) — each needs its own busy flag so a
  // per-disc fetch doesn't show as loading on the collection-level button
  // (and vice versa). Not currently reachable since fetchMetadataOpen and
  // fetchDiscId are mutually exclusive, but the flags must stay independent.
  const [collectionMetadataBusy, setCollectionMetadataBusy] = useState(false)
  const [discMetadataBusy, setDiscMetadataBusy] = useState(false)

  const { data: libraryDefaults } = useQuery<{ delete_media_on_removal: boolean; delete_original_on_upload: boolean }>({
    queryKey: ['settings', 'library-defaults'],
    queryFn: () => apiFetch('/api/v1/settings/library-defaults'),
    staleTime: 60_000,
  })
  const deleteMediaOnRemoval = Boolean(libraryDefaults?.delete_media_on_removal)
  const resolvedDeleteMedia = collection?.delete_media_override ?? deleteMediaOnRemoval

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: async () => (await apiFetch<{ items: LaunchProfile[] }>('/api/v1/profile-items?limit=200')).items,
  })

  const { data: platforms = [] } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/environment-items'),
  })

  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', 'collection', collectionId],
    queryFn: () => apiFetch<LaunchHistory[]>(`/api/v1/game-item-bundle/${collectionId}/launches`),
    enabled: collectionId != null,
  })

  const [execBrowserOpen, setExecBrowserOpen] = useState(false)
  // undefined = not yet loaded; null = never configured (preserve, media may
  // auto-run); [] = explicitly cleared (persist as empty → no auto-run).
  // Using undefined as the load sentinel keeps null distinguishable from [].
  const [launchCommands, setLaunchCommandsState] = useState<string[] | null | undefined>(undefined)

  const {
    localInstalled,
    setLocalInstalled,
    handleToggleInstalled,
    isPending: installedPending,
    installedError,
    confirmOpen: installedConfirmOpen,
    confirmOptions: installedConfirmOptions,
    handleConfirm: handleInstalledConfirm,
    handleCancel: handleInstalledCancel,
  } = useInstalledToggle({ collectionId, detailQueryKey })

  const { form, setFormField, resyncFromCollection } = useEditForm({ collection, formFromCollection })

  useEffect(() => {
    if (collection && !form) {
      setLaunchCommandsState(collection.launch_commands ?? null)
      setLocalInstalled(collection.installed)
    }
  }, [collection, form])

  const { discOrder, setDiscOrder, displayedOrder, isReorderStaged, reset: resetDiscOrder } = useDiscOrder({
    discs: collection?.items ?? [],
    onLaunchDiscChange: (executable_path) => setFormField('executable_path', executable_path),
  })

  const saveMutation = useMutation<GameItemBundleData, Error, EditFormFields>({
    mutationFn: async (f) => {
      await apiFetch<GameItemBundleData>(`/api/v1/game-item-bundle/${collectionId}`, {
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
          environment_item_id : f.environment_item_id  ? parseInt(f.environment_item_id , 10) : null,
          profile_item_id: f.profile_item_id ? parseInt(f.profile_item_id, 10) : null,
          launch_commands: resolveLaunchCommands(launchCommands, collection?.launch_commands),
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
      const reorderStaged = isReorderStaged(currentOrderIds)
      if (reorderStaged && collectionId != null) {
        await apiFetch(`/api/v1/game-item-bundle/${collectionId}/items/reorder`, {
          method: 'PATCH',
          body: JSON.stringify({ disc_order: discOrder }),
        })
      }

      const launchDiscId = reorderStaged
        ? discOrder![0]
        : (collection?.launch_disk_id ?? collection?.items[0]?.id)
      if (launchDiscId != null && collectionId != null) {
        await apiFetch(`/api/v1/game-item-bundle/${collectionId}/items/${launchDiscId}`, {
          method: 'PATCH',
          body: JSON.stringify({
            executable_path: f.executable_path.trim() || null,
            cover_art_path: f.cover_art_path.trim() || null,
          }),
        })
      }

      // Fetch fresh, fully up-to-date collection data (reflecting the collection
      // fields, disc order, and launch-disc executable_path changes above) so
      // the form can resync deterministically in onSuccess rather than relying
      // on invalidateQueries' background refetch timing.
      return refetchEntity()
    },
    onSuccess: (fresh) => {
      resetDiscOrder()
      resyncFromCollection(fresh)
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    },
  })

  const {
    deleteMediaOverrideMutate,
    deleteMediaOverrideError,
    deleteConfirmOpen,
    deleteConfirmOptions,
    handleDeleteConfirm,
    handleDeleteCancel,
    deleting,
    deleteError,
    handleDelete,
  } = useDeleteCollection({
    collectionId,
    title: collection?.title,
    resolvedDeleteMedia,
    detailQueryKey,
    onDeleted: () => navigate('/software'),
  })

  const { flagging, flagError, handleFlagLaunch } = useFlagLaunch({ collectionId, detailQueryKey })

  const xisoConvert = useXisoConvert(collectionId ?? 0)

  if (!collection || !formIsReady(form)) {
    // Mirrors the pre-composition `!collection || !form` guard — while the
    // collection is loaded but the form hasn't seeded yet (one render tick),
    // render no game-only slots at all rather than a partial form. Every
    // hook above still ran unconditionally, satisfying Rules of Hooks.
    return {}
  }

  const eraLabel = ERA_LABELS[collection.era] ?? (collection.era === 'unknown' ? 'Unknown' : collection.era)
  const sortedItems = collection.items.slice().sort((a, b) => a.disc_number - b.disc_number)
  // Single-disc games are collections-of-one — suppress the disc list entirely.
  const isMultiDisc = sortedItems.length > 1
  const showDiscSwapWarning = (collection.era === 'ps1' || collection.era === 'ps2') && isMultiDisc

  // Staged order takes precedence over the server's disc_number order once
  // the user has dragged/moved a disc, so the "Launch File" field below and
  // the "Launch target" badge in the disc list both reflect the not-yet-saved
  // choice consistently.
  const currentLaunchDisc =
    sortedItems.find((i) => i.id === displayedOrder[0]) ?? sortedItems[0]

  const effectiveProfileId = form.profile_item_id
    ? parseInt(form.profile_item_id, 10)
    : (collection.profile_item_id ?? null)
  // Launch gating is driven solely by the backend-computed launch_blocked_reason
  // now, no parallel client-side profile check. effectiveProfileId is still used
  // as the launch payload so a saved profile override is honored, but it no
  // longer decides whether the button is enabled.
  const launchGate = launchGateFromReason(collection.launch_blocked_reason, isLaunching)

  const storageKey = `fetch_metadata_${window.location.pathname}_${activeProvider}`
  const activeDisc = fetchDiscId != null ? sortedItems.find((d) => d.id === fetchDiscId) : undefined

  return {
    eraLabel,
    launchCount: collection.launch_count,
    lastLaunchedAt: collection.last_launched_at,
    launchHistory,

    topControl: (
      <section className="space-y-3 rounded-md border border-neutral-200 bg-neutral-50 px-4 py-3 dark:border-surface-700 dark:bg-surface-900">
        <label
          htmlFor="delete-media-override"
          className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300"
        >
          <input
            type="checkbox"
            id="delete-media-override"
            checked={resolvedDeleteMedia}
            onChange={(e) => deleteMediaOverrideMutate(e.target.checked)}
            className="h-4 w-4"
          />
          Delete all files/folders when you delete this in Peach 1UP?
        </label>
        {deleteMediaOverrideError && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400">{deleteMediaOverrideError}</p>
        )}
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
    ),

    metaAfter: (
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
        {collection.metadata_fetched_at && (
          <div>
            <span className="font-medium">Metadata fetched:</span>{' '}
            {new Date(collection.metadata_fetched_at).toLocaleDateString()}
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
              loading={installedPending}
            >
              {localInstalled ? 'Mark as not installed' : 'Mark as installed'}
            </Button>
          </div>
        )}
      </>
    ),

    editForm: {
      item: {
        era: form.era || collection.era,
        file_path: currentLaunchDisc?.file_path,
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
    },

    advancedSection: {
      item: { launch_review_flagged: collection.launch_review_flagged },
      flagging,
      flagError,
      onFlagLaunch: handleFlagLaunch,
      launchCommands: launchCommands ?? null,
      setLaunchCommands: setLaunchCommandsState,
    },

    fetchMetadataAction: isOwner ? (
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
          Metadata
        </h2>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              if (confirmRefetchIfAlreadyFetched(collection.metadata_fetched_at)) setFetchMetadataOpen(true)
            }}
            disabled={!metadataProviderEnabled || collectionMetadataBusy}
            loading={collectionMetadataBusy}
            title={!metadataProviderEnabled ? `${activeProviderLabel} credentials not configured — set them in Settings > Advanced` : undefined}
          >
            Fetch Metadata
          </Button>
          {!isMultiDisc && sortedItems[0] && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                if (confirmRefetchIfAlreadyFetched(sortedItems[0].metadata_fetched_at)) setFetchDiscId(sortedItems[0].id)
              }}
              disabled={!metadataProviderEnabled || discMetadataBusy}
              loading={discMetadataBusy && fetchDiscId === sortedItems[0].id}
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
    ) : null,

    beforeLaunch: (
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
                    onClick={() => {
                      if (confirmRefetchIfAlreadyFetched(disc.metadata_fetched_at)) setFetchDiscId(disc.id)
                    }}
                    disabled={!metadataProviderEnabled || discMetadataBusy}
                    loading={discMetadataBusy && fetchDiscId === disc.id}
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
    ),

    onLaunch: () => launch(effectiveProfileId),
    launchDisabled: launchGate.launchDisabled,
    launchButtonLabel: launchGate.launchButtonLabel,
    launchNote: launchGate.launchNote ? (
      <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
        {launchGate.launchNote}
      </p>
    ) : undefined,
    launchErrorAction: launchErrorType === 'xbox_dvd_rip' ? (
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
    ) : undefined,

    afterContent: (
      <>
        <LinkedItemsSection items={collection.linked_items} />

        <FetchMetadataModal
          open={fetchMetadataOpen}
          onClose={() => setFetchMetadataOpen(false)}
          entityType="game_item_bundle"
          entityId={collection.id}
          entityTitle={collection.title}
          currentContentRating={collection.content_rating}
          storageKey={storageKey}
          activeProviderLabel={activeProviderLabel}
          onSuccess={async () => {
            queryClient.invalidateQueries({ queryKey: detailQueryKey })
            // Matches EntityListPage's own invalidate() key for the game list
            // (config.domain, 'list') — was the pre-cutover Games.tsx-only
            // ['library'] key, which stopped matching anything once Games.tsx
            // moved onto EntityListPage's ['game', 'list', ...] list query.
            queryClient.invalidateQueries({ queryKey: ['game', 'list'] })
            // Fetch fresh data directly and resync the edit form — the form is only
            // built from `collection` once (see the formIsReady guard above), so it
            // would otherwise show stale publisher/description/category/rating/
            // cover art fields until a full page reload even after the invalidated
            // query refetches in the background.
            const fresh = await refetchEntity()
            resyncFromCollection(fresh)
          }}
          onBusyChange={setCollectionMetadataBusy}
        />

        {fetchDiscId != null && activeDisc != null && (
          <FetchMetadataModal
            open={fetchDiscId != null}
            onClose={() => setFetchDiscId(null)}
            entityType="game_item"
            entityId={fetchDiscId}
            entityTitle={activeDisc.file_path.split(/[\\/]/).pop() ?? collection.title}
            storageKey={`${storageKey}#disc-${fetchDiscId}`}
            activeProviderLabel={activeProviderLabel}
            onSuccess={async () => {
              queryClient.invalidateQueries({ queryKey: detailQueryKey })
              queryClient.invalidateQueries({ queryKey: ['game', 'list'] })
              const fresh = await refetchEntity()
              resyncFromCollection(fresh)
              setFetchDiscId(null)
            }}
            onBusyChange={setDiscMetadataBusy}
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

        {installedError && (
          <p role="alert" className="sr-only">{installedError}</p>
        )}
      </>
    ),
  }
}

// Games.tsx keeps its existing two-button/two-modal layout (Add Media, Scan
// Directory) unchanged, both now point at the shared LibraryModal instead of
// the former games-only AddMediaModal/ScanModal, with every sub-feature
// (multi-disc, folder upload, browse-server-path import) still enabled so
// behavior is identical to before this extraction. Declared above
// gameDomainConfig (which now references both) to avoid a temporal-dead-zone
// reference at module init.
export const gameUploadModalConfig: LibraryModalConfig = {
  mode: 'upload',
  // Migrated off the old games-only /api/v1/game-items/uploads/* path onto
  // the route-per-domain shape: /api/v1/uploads/software-games/*.
  uploadDomain: 'software_games',
  modalTitle: 'Add Media',
  entityLabel: 'game',
  entityLabelPlural: 'games',
  supportsMultiDisc: true,
  supportsFolderMode: true,
  importFromPathApiPath: '/api/v1/game-items/import-from-path',
}

export const gameScanModalConfig: LibraryModalConfig = {
  mode: 'scan',
  uploadDomain: 'software_games',
  modalTitle: 'Scan Library',
  entityLabel: 'game',
  entityLabelPlural: 'games',
}

// Game's cover art lives on the leaf item (display/launch disk id
// indirection) — see getGameCoverArt in CollectionCard.tsx, reused as-is.
export const gameDomainConfig: EntityDomainConfig<GameItemBundleData> = {
  domain: 'game',
  routeBase: GAME_ROUTE_BASE,
  listApiPath: '/api/v1/game-items',
  bundleApiPath: gameBundleApiPath,
  tagEntityType: 'game_item_bundle',
  entityLabel: 'game',
  entityLabelPlural: 'games',
  coverArt: getGameCoverArt,
  launchTargetType: 'collection',
  identifierParam: 'slug',
  backLabel: 'Back to Software',
  showDescriptionMeta: false,
  filterRestrictionUsers: (users) => users.filter((u) => !u.is_owner),
  renderExtras: useGameDetailExtras,
  // Era/profile/tag filter bar (EntityListPage.tsx). Confirmed backend
  // support: GET /api/v1/game-items (game_item_bundles.py:list_game_items)
  // accepts `era`, `profile_assigned`, and `tag` query params today.
  filters: { era: true, profileAssigned: true, tag: true },
  // Sort control (EntityListPage.tsx). Confirmed backend support: GET
  // /api/v1/game-items (game_item_bundles.py:list_game_items) accepts `sort`
  // ("title" | "date_added") today, same shared value set as App and Media.
  sortOptions: SOFTWARE_SORT_OPTIONS,
  // Games.tsx's own two-button/two-modal layout (Add Media, Scan Directory),
  // now driven through EntityListPage instead of the former bespoke page.
  uploadConfig: gameUploadModalConfig,
  scanConfig: gameScanModalConfig,
  // Multi-disc display-disk selection — data side. Mirrors Games.tsx's former
  // handleSetDisplayDisk exactly (same endpoint/body). EntityListPage gates
  // all use of this behind `config.multiDisc` being present, and invalidates
  // the list query itself after the write completes.
  multiDisc: {
    items: (bundle) => bundle.items.map((i) => ({
      id: i.id,
      disc_number: i.disc_number,
      cover_art_url: i.cover_art_url,
    })),
    displayDiskId: (bundle) => bundle.display_disk_id,
    launchDiskId: (bundle) => bundle.launch_disk_id,
    onSetDisplayDisk: async (entityId, discId) => {
      await apiFetch(`/api/v1/game-item-bundle/${entityId}`, {
        method: 'PATCH',
        body: JSON.stringify({ display_disk_id: discId }),
      })
    },
  },
  // Delete-media-override + two-step confirm-token delete flow, ported from
  // Games.tsx's handleRemove (same endpoints, same PATCH-then-confirm-token
  // sequence — see EntityListPage.tsx's handleRemove, deleteConfig branch).
  deleteConfig: {
    bundleByIdApiPath: (id) => `/api/v1/game-item-bundle/${id}`,
    resolveDeleteMediaOverride: (bundle) => bundle.delete_media_override,
  },
  // Game's grid card is CollectionCard (stacked-disc layers, era placeholder,
  // stack-count/divergence badges, hover play button) — not EntityCard's
  // generic layout. Ported as-is from Games.tsx/CollectionCard.tsx so the
  // grid's visuals and disc-strip interaction are pixel-for-pixel identical
  // to the pre-cutover page, not just data-plumbing-equivalent.
  renderCard: ({ entity, onRemove, onSetDisplayDisk }) => (
    <CollectionCard collection={entity} onRemove={onRemove} onSetDisplayDisk={onSetDisplayDisk} />
  ),
}
