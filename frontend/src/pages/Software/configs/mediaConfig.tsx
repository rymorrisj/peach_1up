import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useEditForm } from '@/hooks/useEditForm'
import { formFromCollection, type SoftwareMediaForm } from '../types/mediaForm'
import { MediaEditForm } from '../components/MediaEditForm'
import type { LibraryModalConfig } from '../components/LibraryModal'
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

// Media had no creation UI at all before this. Mode is 'upload' only
// (no scan support exists on the backend for this domain, unlike Game), and
// no multi-disc/folder/browse-import sub-features since archival media
// (audio, text, image, video, per dev_docs/v2/03_media_archive.md) is
// standalone-item-first, not a multi-disc collection concept like Game.
export const mediaUploadModalConfig: LibraryModalConfig = {
  mode: 'upload',
  // PROVISIONAL CONTRACT. See chunkedUpload.ts. No live backend endpoint
  // exists for this target_type yet: the real Media upload route today
  // (POST /api/v1/media-items/upload) is a single-shot, non-chunked,
  // two-step stage-then-create flow, not this chunked init/chunks/complete
  // shape. Load-bearing assumption, revisit once the discovery session
  // confirms whether Media gets a chunked endpoint or this modal needs a
  // non-chunked upload path for this target_type instead.
  targetType: 'media_item_bundle',
  modalTitle: 'Add Media',
  entityLabel: 'media item',
  entityLabelPlural: 'media',
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
  uploadConfig: mediaUploadModalConfig,
}
