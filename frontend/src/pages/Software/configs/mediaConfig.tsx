import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import { useEditForm } from '@/hooks/useEditForm';
import { formFromCollection, type SoftwareMediaForm } from '../types/mediaForm';
import { MediaEditForm } from '../components/MediaEditForm';
import { LinkedItemsSection } from '../components/LinkedItemsSection';
import { FilesSection } from '../components/FilesSection';
import type { LibraryModalConfig } from '../components/LibraryModal';
import type {
  EntityBundleBase,
  EntityDetailExtras,
  EntityDetailExtrasContext,
  EntityDomainConfig,
} from '../types';
import { SOFTWARE_SORT_OPTIONS, MEDIA_ROUTE_BASE } from '../types';

export interface MediaItemLeaf {
  id: number;
  media_item_bundle_id: number | null;
  file_path: string;
  file_url: string | null;
  file_size_bytes: number | null;
  media_kind: string;
  cover_art_path: string | null;
  cover_art_url: string | null;
}

export interface MediaItemBundleData extends EntityBundleBase {
  media_kind: string;
  cover_art_path: string | null;
  cover_art_url: string | null;
  items: MediaItemLeaf[];
}

// Minimal edit form: title, description, cover_art_path. A single PATCH,
// no multi-step disc/leaf sequence like Game's since cover_art_path lives
// directly on the bundle (see formFromCollection in types/mediaForm.ts).
function useMediaDetailExtras(
  ctx: EntityDetailExtrasContext<MediaItemBundleData>,
): EntityDetailExtras {
  const collection = ctx.entity;
  const collectionId = ctx.entityId;
  const { detailQueryKey, refetchEntity } = ctx;
  const queryClient = useQueryClient();

  const { form, setFormField, resyncFromCollection } = useEditForm({
    collection,
    formFromCollection,
  });

  const saveMutation = useMutation<MediaItemBundleData, Error, SoftwareMediaForm>({
    mutationFn: async (f) => {
      await apiFetch<MediaItemBundleData>(`/api/v1/media-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: f.title.trim() || undefined,
          description: f.description.trim() || null,
          cover_art_path: f.cover_art_path.trim() || null,
        }),
      });
      return refetchEntity();
    },
    onSuccess: (fresh) => {
      resyncFromCollection(fresh);
      queryClient.invalidateQueries({ queryKey: detailQueryKey });
    },
  });

  // Additive to handleSetCoverArt below, not a replacement: this leaves the
  // media item's own cover_art_path untouched and instead pushes the
  // selected file onto every linked game_item_bundle's own cover art (see
  // POST /media-item-bundle/{id}/apply-cover-art-to-linked-games). Applies
  // to every linked game at once (no per-link picker exists in this UI, and
  // MediaLink itself has no cardinality limit), consistent with the two-
  // sided can_manage_media + can_manage_game permission check the backend
  // route enforces. Declared here, alongside saveMutation, rather than below
  // the early return, since hooks must run unconditionally on every render.
  const applyCoverArtToGamesMutation = useMutation<number[], Error, string>({
    mutationFn: (filePath) =>
      apiFetch<number[]>(
        `/api/v1/media-item-bundle/${collectionId}/apply-cover-art-to-linked-games`,
        {
          method: 'POST',
          body: JSON.stringify({ file_path: filePath }),
        },
      ),
    onSuccess: () => {
      // The response is a list of affected game ids, but game detail is cached
      // by slug (not id), so there's no exact per-game key to target, invalidate
      // every currently-cached game list/detail query instead of guessing slugs.
      queryClient.invalidateQueries({ queryKey: ['game', 'list'] });
      queryClient.invalidateQueries({ queryKey: ['game', 'detail'] });
    },
  });

  // Dedicated mutation for "Set as cover art" from the file list, deliberately
  // separate from saveMutation: reusing saveMutation would (a) PATCH the live
  // edit-form state alongside cover_art_path, silently committing any
  // half-typed title/description edit sitting in the form, and (b) make the
  // unrelated Details card flash "Saved"/disable its Save button, since the
  // two actions would share one mutation's pending/success state.
  const setCoverArtMutation = useMutation<MediaItemBundleData, Error, string>({
    mutationFn: async (filePath) => {
      await apiFetch<MediaItemBundleData>(`/api/v1/media-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ cover_art_path: filePath || null }),
      });
      return refetchEntity();
    },
    onSuccess: (fresh) => {
      resyncFromCollection(fresh);
      queryClient.invalidateQueries({ queryKey: detailQueryKey });
    },
  });

  if (!collection || form == null) {
    return {};
  }

  function handleSetCoverArt(filePath: string) {
    setCoverArtMutation.mutate(filePath);
  }

  const linkedGameItems = (collection.linked_items ?? [])
    .filter((ref) => ref.entity_type === 'game_item_bundle')
    .map((ref) => ({ entity_id: ref.entity_id, title: ref.title }));

  return {
    editFormContent: (
      <MediaEditForm
        form={form}
        setField={setFormField}
        handleSave={() => saveMutation.mutate(form)}
        saving={saveMutation.isPending}
        saveError={
          saveMutation.isError
            ? saveMutation.error instanceof ApiError
              ? saveMutation.error.detail
              : 'Failed to save.'
            : null
        }
        saveSuccess={saveMutation.isSuccess}
      />
    ),
    afterContent: (
      <>
        <FilesSection
          items={collection.items}
          currentCoverArtPath={collection.cover_art_path}
          onSetCoverArt={handleSetCoverArt}
          settingCoverArt={setCoverArtMutation.isPending}
          linkedGameItems={linkedGameItems}
          onApplyCoverArtToGames={(filePath) => applyCoverArtToGamesMutation.mutate(filePath)}
          applyingCoverArtToGames={applyCoverArtToGamesMutation.isPending}
        />
        {applyCoverArtToGamesMutation.isSuccess && (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Updated cover art for {applyCoverArtToGamesMutation.data.length} linked game
            {applyCoverArtToGamesMutation.data.length === 1 ? '' : 's'}.
          </p>
        )}
        {applyCoverArtToGamesMutation.isError && (
          <p className="text-xs text-red-600 dark:text-red-400">
            {applyCoverArtToGamesMutation.error instanceof ApiError
              ? applyCoverArtToGamesMutation.error.detail
              : 'Failed to update linked game cover art.'}
          </p>
        )}
        <LinkedItemsSection items={collection.linked_items} />
      </>
    ),
  };
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
  // POST /api/v1/media-items/upload contract exactly.
  uploadDomain: 'software_media',
  modalTitle: 'Add Media',
  entityLabel: 'media item',
  entityLabelPlural: 'media',
};

// Media has no launch capability at all (no launchTargetType), and its cover
// art lives directly on the bundle rather than a leaf item (see discovery:
// cover_art_url is bundle-level for Media, leaf-level for Game/App).
export const mediaDomainConfig: EntityDomainConfig<MediaItemBundleData> = {
  domain: 'media',
  routeBase: MEDIA_ROUTE_BASE,
  listApiPath: '/api/v1/media-item-bundles',
  bundleApiPath: (id) => `/api/v1/media-item-bundle/${id}`,
  tagEntityType: 'media_item_bundle',
  entityLabel: 'media item',
  entityLabelPlural: 'media',
  coverArt: (bundle) => bundle.cover_art_url ?? null,
  // The edit form already renders Description; showing it a second time as
  // detail-page meta text double-displays it (matches gameConfig).
  showDescriptionMeta: false,
  // The owner can never be restricted (backend hard-exempts is_owner in every
  // restriction filter, see backend/core/dependencies.py), so it should not
  // appear in the Restrictions checkbox list at all, matching gameConfig.
  filterRestrictionUsers: (users) => users.filter((u) => !u.is_owner),
  useRenderExtras: useMediaDetailExtras,
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
};
