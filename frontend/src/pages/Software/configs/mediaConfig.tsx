import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useEditForm } from '@/hooks/useEditForm'
import { formFromCollection, type SoftwareMediaForm } from '../types/mediaForm'
import { MediaEditForm } from '../components/MediaEditForm'
import type { LibraryModalConfig } from '../components/LibraryModal'
import type { EntityBundleBase, EntityDetailExtras, EntityDetailExtrasContext, EntityDomainConfig } from '../types'
import { SOFTWARE_SORT_OPTIONS } from '../types'

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

// Best-effort media_kind inference from the uploaded file's extension. The
// chunked upload transport never asks for media_kind (it only moves bytes),
// and unlike Game/App this domain's finalize deliberately does not create a
// DB row (see backend/service/uploads/software_media.py), media_kind is a
// human/DB-facing field the upload step doesn't know about, so it has to be
// guessed here for the follow-up create call. Unrecognized extensions fall
// back to "text" (the closest thing to a generic-document catch-all in
// MediaKind) rather than blocking the upload; the user can correct it from
// the detail page's edit form afterward.
function inferMediaKind(fileName: string): 'audio' | 'text' | 'image' | 'video' {
  const ext = fileName.slice(fileName.lastIndexOf('.') + 1).toLowerCase()
  if (['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma'].includes(ext)) return 'audio'
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'tif'].includes(ext)) return 'image'
  if (['mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'm4v'].includes(ext)) return 'video'
  return 'text'
}

// Media had no creation UI at all before this. Mode is 'upload' only
// (no scan support exists on the backend for this domain, unlike Game), and
// no multi-disc/folder/browse-import sub-features since archival media
// (audio, text, image, video, per dev_docs/v2/03_media_archive.md) is
// standalone-item-first, not a multi-disc collection concept like Game.
export const mediaUploadModalConfig: LibraryModalConfig = {
  mode: 'upload',
  // Resolved: dev_docs/v2/03_media_archive.md's "archival Media domain" and
  // this Software Media sub-tab turned out to be the same shipped entity
  // (MediaItem/MediaItemBundle, backend/models/media.py), there is no
  // second Media domain. Its chunked endpoint
  // (/api/v1/uploads/software-media/*) mirrors the existing single-shot
  // POST /api/v1/media-items/upload contract exactly: finalize only stages
  // bytes and returns {path, slug, size_bytes}, it does not create the row.
  // createFromUpload below makes that second call.
  uploadDomain: 'software_media',
  modalTitle: 'Add Media',
  entityLabel: 'media item',
  entityLabelPlural: 'media',
  createFromUpload: async (body, fileName) => {
    const title = fileName.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ').trim() || fileName
    await apiFetch('/api/v1/media-items', {
      method: 'POST',
      body: JSON.stringify({
        title,
        media_kind: inferMediaKind(fileName),
        file_path: body.path,
        file_size_bytes: body.size_bytes ?? null,
      }),
    })
  },
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
  // Media has no era/profile concept, but tags are shared across every
  // domain (GET /api/v1/media-item-bundles, media.py:list_media_item_bundles,
  // accepts `tag` the same way Game/App's list endpoints do), so it opts
  // into the tag filter only. This is Media's first `filters` config; it
  // previously omitted the field entirely and rendered no filter bar at all.
  filters: { tag: true },
  // Sort control (EntityListPage.tsx). GET /api/v1/media-item-bundles
  // (media.py:list_media_item_bundles) accepts the same `sort`
  // ("title" | "date_added") param as Game/App.
  sortOptions: SOFTWARE_SORT_OPTIONS,
}
