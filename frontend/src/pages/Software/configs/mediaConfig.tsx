import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useEditForm } from '@/hooks/useEditForm'
import { formFromCollection, type SoftwareMediaForm } from '../types/mediaForm'
import { MediaEditForm } from '../components/MediaEditForm'
import type { EntityBundleBase, EntityDetailExtras, EntityDetailExtrasContext, EntityDomainConfig } from '../types'

export interface MediaItemLeaf {
  id: number
  media_item_bundle_id: number | null
  file_path: string
  cover_art_path: string | null
  cover_art_url: string | null
}

export interface MediaItemBundleData extends EntityBundleBase {
  media_kind: string
  cover_art_path: string | null
  cover_art_url: string | null
  items: MediaItemLeaf[]
}

// Minimal edit form: title, description, cover_art_path. A single PATCH,
// no multi-step disc/leaf sequence like Game's since cover_art_path lives
// directly on the bundle (see formFromCollection in types/mediaForm.ts).
function useMediaDetailExtras(ctx: EntityDetailExtrasContext<MediaItemBundleData>): EntityDetailExtras {
  const collection = ctx.entity
  const collectionId = ctx.entityId
  const { detailQueryKey, refetchEntity } = ctx
  const queryClient = useQueryClient()

  const { form, setFormField, resyncFromCollection } = useEditForm({ collection, formFromCollection })

  const saveMutation = useMutation<MediaItemBundleData, Error, SoftwareMediaForm>({
    mutationFn: async (f) => {
      await apiFetch<MediaItemBundleData>(`/api/v1/media-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: f.title.trim() || undefined,
          description: f.description.trim() || null,
          cover_art_path: f.cover_art_path.trim() || null,
        }),
      })
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

  return {
    editFormContent: (
      <MediaEditForm
        form={form}
        setField={setFormField}
        handleSave={() => saveMutation.mutate(form)}
        saving={saveMutation.isPending}
        saveError={saveMutation.isError
          ? (saveMutation.error instanceof ApiError ? saveMutation.error.detail : 'Failed to save.')
          : null}
        saveSuccess={saveMutation.isSuccess}
      />
    ),
  }
}

// Media has no launch capability at all (no launchTargetType), and its cover
// art lives directly on the bundle rather than a leaf item (see discovery:
// cover_art_url is bundle-level for Media, leaf-level for Game/App).
export const mediaDomainConfig: EntityDomainConfig<MediaItemBundleData> = {
  domain: 'media',
  routeBase: '/software/media',
  listApiPath: '/api/v1/media-item-bundles',
  bundleApiPath: (id) => `/api/v1/media-item-bundle/${id}`,
  tagEntityType: 'media_item_bundle',
  entityLabel: 'media item',
  entityLabelPlural: 'media',
  coverArt: (bundle) => bundle.cover_art_url ?? null,
  renderExtras: useMediaDetailExtras,
}
