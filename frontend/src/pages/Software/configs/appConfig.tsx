import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useEditForm } from '@/hooks/useEditForm'
import { formFromCollection, type SoftwareAppForm } from '../types/appForm'
import { AppEditForm } from '../components/AppEditForm'
import { LinkedItemsSection } from '../components/LinkedItemsSection'
import type { LibraryModalConfig } from '../components/LibraryModal'
import type { EntityBundleBase, EntityDetailExtras, EntityDetailExtrasContext, EntityDomainConfig } from '../types'
import { resolveLeafCoverArt, launchGateFromReason, SOFTWARE_SORT_OPTIONS, APP_ROUTE_BASE } from '../types'
import type { components } from '@shared/types'

type Platform = components['schemas']['EnvironmentItemRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']

export interface AppItemLeaf {
  id: number
  app_item_bundle_id: number
  file_path: string
  executable_path: string | null
  cover_art_path: string | null
  cover_art_url: string | null
}

export interface AppItemBundleData extends EntityBundleBase {
  era: string
  is_pc: boolean
  category: string | null
  publisher: string | null
  developer: string | null
  year: number | null
  installed: boolean
  // None = inherit the global delete_media_on_removal setting; true/false
  // overrides it. Present on the backend's AppItemBundleRead (see
  // backend/models/app.py) but previously unused by the frontend, added for
  // EntityListPage's deleteConfig (see appDomainConfig below).
  delete_media_override: boolean | null
  environment_item_id: number | null
  profile_item_id: number | null
  launch_disk_id: number | null
  display_disk_id: number | null
  last_launched_at: string | null
  launch_count: number
  // Backend-computed pre-launch gate: "no_profile" | "no_environment" | null.
  // The single source of truth for launch gating (see launchGateFromReason).
  launch_blocked_reason: string | null
  items: AppItemLeaf[]
}

// Minimal edit form: title, description, cover_art_path, era, environment_item_id
// (is_pc is derived from era, kept in sync by AppEditForm rather than edited
// directly, see types/appForm.ts). Save is a two-step PATCH mirroring Game's
// bundle-fields-then-leaf-fields sequence, since App keeps cover_art_path on
// its (single, collection-of-one) leaf item, not the bundle, confirmed
// against backend/models/app.py rather than assumed.
function useAppDetailExtras(ctx: EntityDetailExtrasContext<AppItemBundleData>): EntityDetailExtras {
  const collection = ctx.entity
  const collectionId = ctx.entityId
  const { detailQueryKey, refetchEntity, isLaunching } = ctx
  const queryClient = useQueryClient()

  const { data: platforms = [] } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/environment-items'),
  })

  // App has no dedicated collection-launches route like Game's
  // /game-item-bundle/{id}/launches, so this uses the generic scoped launches
  // endpoint filtered to this app bundle. Same query-key prefix ('launches') as
  // Game so a bulk-delete elsewhere invalidates it too.
  const { data: launchHistory = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches', 'app', collectionId],
    queryFn: () =>
      apiFetch<LaunchHistory[]>(`/api/v1/launches?target_id=${collectionId}&target_type=app_item_bundle`),
    enabled: collectionId != null,
  })

  const { form, setFormField, resyncFromCollection } = useEditForm({ collection, formFromCollection })

  const saveMutation = useMutation<AppItemBundleData, Error, SoftwareAppForm>({
    mutationFn: async (f) => {
      await apiFetch<AppItemBundleData>(`/api/v1/app-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: f.title.trim() || undefined,
          description: f.description.trim() || null,
          era: f.era || null,
          environment_item_id: f.environment_item_id ? parseInt(f.environment_item_id, 10) : null,
        }),
      })

      const leafId = collection?.display_disk_id ?? collection?.launch_disk_id ?? collection?.items[0]?.id
      if (leafId != null) {
        await apiFetch(`/api/v1/app-item/${leafId}`, {
          method: 'PATCH',
          body: JSON.stringify({ cover_art_path: f.cover_art_path.trim() || null }),
        })
      }

      return refetchEntity()
    },
    onSuccess: (fresh) => {
      resyncFromCollection(fresh)
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    },
  })

  if (!collection || form == null) {
    return {}
  }

  // Launch gating mirrors Game: driven solely by the backend launch_blocked_reason,
  // no client-side profile/environment check. Apps have no in-form profile picker,
  // so onLaunch launches with the stored profile (default null payload).
  const launchGate = launchGateFromReason(collection.launch_blocked_reason, isLaunching)

  return {
    era: collection.era,
    year: collection.year,
    publisher: collection.publisher,
    launchCount: collection.launch_count,
    lastLaunchedAt: collection.last_launched_at,
    launchHistory,
    launchDisabled: launchGate.launchDisabled,
    launchButtonLabel: launchGate.launchButtonLabel,
    launchNote: launchGate.launchNote ? (
      <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
        {launchGate.launchNote}
      </p>
    ) : undefined,
    editFormContent: (
      <AppEditForm
        form={form}
        setField={setFormField}
        handleSave={() => saveMutation.mutate(form)}
        saving={saveMutation.isPending}
        saveError={saveMutation.isError
          ? (saveMutation.error instanceof ApiError ? saveMutation.error.detail : 'Failed to save.')
          : null}
        saveSuccess={saveMutation.isSuccess}
        platforms={platforms}
      />
    ),
    afterContent: <LinkedItemsSection items={collection.linked_items} />,
  }
}

// App had no creation UI at all before this. Mode is 'upload' only (no scan
// support on the backend for this domain), and no multi-disc/folder/browse-
// import sub-features: AppItem has no disc_number/multi-part concept the way
// GameItem does, so a bundle is always a single uploaded item here.
export const appUploadModalConfig: LibraryModalConfig = {
  mode: 'upload',
  // Resolved: backend/service/uploads/software_apps.py now implements a real
  // chunked upload path (/api/v1/uploads/software-apps/*) whose finalize
  // creates the AppItemBundle + AppItem row directly, same shape as Game.
  // era is left "unknown" (no detection, matching apps.py's existing
  // create_app_item_bundle), editable from the detail page after upload.
  // The backend also accepts kind="folder" (multi-part installs), but the
  // upload UI here stays single-file-only for now, supportsFolderMode is
  // deliberately not set.
  uploadDomain: 'software_apps',
  modalTitle: 'Add App',
  entityLabel: 'app',
  entityLabelPlural: 'apps',
}

// App's cover art lives on the leaf item (same indirection as Game — see
// resolveLeafCoverArt). Launch is domain-enabled ('app' targetType) but
// per-entity gated to PC apps only via isLaunchable (bundle.is_pc).
export const appDomainConfig: EntityDomainConfig<AppItemBundleData> = {
  domain: 'app',
  routeBase: APP_ROUTE_BASE,
  listApiPath: '/api/v1/app-items',
  bundleApiPath: (id) => `/api/v1/app-item-bundle/${id}`,
  tagEntityType: 'app_item_bundle',
  entityLabel: 'app',
  entityLabelPlural: 'apps',
  coverArt: (bundle) => resolveLeafCoverArt(bundle.items, bundle.display_disk_id, bundle.launch_disk_id),
  launchTargetType: 'app',
  isLaunchable: (bundle) => bundle.is_pc,
  // The owner can never be restricted (backend hard-exempts is_owner in every
  // restriction filter, see backend/core/dependencies.py), so it should not
  // appear in the Restrictions checkbox list at all, matching gameConfig.
  filterRestrictionUsers: (users) => users.filter((u) => !u.is_owner),
  renderExtras: useAppDetailExtras,
  // Era/profile/tag filter bar (EntityListPage.tsx). Backend support added
  // alongside this: GET /api/v1/app-items (apps.py:list_apps) now accepts
  // `era`, `profile_assigned`, and `tag` query params, mirroring Game's
  // list_game_items exactly.
  filters: { era: true, profileAssigned: true, tag: true },
  // Sort control (EntityListPage.tsx). Backend support added alongside this:
  // GET /api/v1/app-items (apps.py:list_apps) now accepts `sort`
  // ("title" | "date_added"), mirroring Game's list_game_items exactly.
  sortOptions: SOFTWARE_SORT_OPTIONS,
  uploadConfig: appUploadModalConfig,
  // App's backend mirrors Game's full delete contract (confirm-delete token
  // issue/consume, delete_media_override on AppItemBundleUpdate, see
  // backend/api/routes/apps.py and backend/models/app.py), unlike Media,
  // whose delete_media_item_bundle route takes no confirmation_token at all.
  // Wiring this also fixes a real bug: apps.py's DELETE route declares
  // `confirmation_token: str = Query(...)` (required, no default), so
  // EntityListPage's previous plain `DELETE /app-item-bundle/{id}` (no query
  // param) would 422 on every attempt to remove an app from this list page.
  deleteConfig: {
    bundleByIdApiPath: (id) => `/api/v1/app-item-bundle/${id}`,
    resolveDeleteMediaOverride: (bundle) => bundle.delete_media_override,
  },
}
