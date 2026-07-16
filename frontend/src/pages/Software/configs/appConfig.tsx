import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useEditForm } from '@/hooks/useEditForm'
import { formFromCollection, type SoftwareAppForm } from '../types/appForm'
import { AppEditForm } from '../components/AppEditForm'
import type { LibraryModalConfig } from '../components/LibraryModal'
import type { EntityBundleBase, EntityDetailExtras, EntityDetailExtrasContext, EntityDomainConfig } from '../types'
import { resolveLeafCoverArt, launchGateFromReason } from '../types'
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
  }
}

// App had no creation UI at all before this. Mode is 'upload' only (no scan
// support on the backend for this domain), and no multi-disc/folder/browse-
// import sub-features: AppItem has no disc_number/multi-part concept the way
// GameItem does, so a bundle is always a single uploaded item here.
export const appUploadModalConfig: LibraryModalConfig = {
  mode: 'upload',
  // PROVISIONAL CONTRACT. See chunkedUpload.ts. No live backend endpoint
  // exists for this target_type at all today: apps.py's only creation route
  // (POST /api/v1/app-items) takes a pre-existing file_path and has zero
  // upload/file-transport mechanism of its own. This is the most speculative,
  // most load-bearing provisional-contract assumption in this refactor.
  // App uploads cannot function until the backend actually implements a
  // chunked (or any) upload path for "app_item".
  targetType: 'app_item',
  modalTitle: 'Add App',
  entityLabel: 'app',
  entityLabelPlural: 'apps',
}

// App's cover art lives on the leaf item (same indirection as Game — see
// resolveLeafCoverArt). Launch is domain-enabled ('app' targetType) but
// per-entity gated to PC apps only via isLaunchable (bundle.is_pc).
export const appDomainConfig: EntityDomainConfig<AppItemBundleData> = {
  domain: 'app',
  routeBase: '/software/apps',
  listApiPath: '/api/v1/app-items',
  bundleApiPath: (id) => `/api/v1/app-item-bundle/${id}`,
  tagEntityType: 'app_item_bundle',
  entityLabel: 'app',
  entityLabelPlural: 'apps',
  coverArt: (bundle) => resolveLeafCoverArt(bundle.items, bundle.display_disk_id, bundle.launch_disk_id),
  launchTargetType: 'app',
  isLaunchable: (bundle) => bundle.is_pc,
  renderExtras: useAppDetailExtras,
  uploadConfig: appUploadModalConfig,
}
