import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import { useConfirm } from './useConfirm';
import { useConfirmToken } from './useConfirmToken';
import { useRatingChangeConfirm } from './useRatingChangeConfirm';

interface UseDeleteCollectionOptions {
  collectionId: number | undefined;
  title: string | undefined;
  resolvedDeleteMedia: boolean;
  detailQueryKey: unknown[];
  onDeleted: () => void;
}

// Persistent per-collection override for delete_media_on_removal, checking
// or unchecking PATCHes immediately, no staging behind Save Changes, plus
// the destructive two-step confirm-token delete flow.
//
// The standalone mutation below (from the page's own checkbox) is the only
// path that persists delete_media_override. handleDelete never PATCHes: the
// delete-confirm dialog's checkbox value is always sent as delete_media on
// the DELETE itself, unconditionally (not gated on differing from the
// possibly stale resolvedDeleteMedia cache), so it is still the single
// source of truth for this delete regardless of cache freshness, and
// nothing is written if the user cancels the rating-change prompt.
export function useDeleteCollection({
  collectionId,
  title,
  resolvedDeleteMedia,
  detailQueryKey,
  onDeleted,
}: UseDeleteCollectionOptions) {
  const queryClient = useQueryClient();

  const deleteMediaOverrideMutation = useMutation<void, Error, boolean>({
    mutationFn: (value) => {
      if (collectionId == null) return Promise.resolve();
      return apiFetch(`/api/v1/game-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ delete_media_override: value }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: detailQueryKey });
      // Also invalidate the grid/list query, its own delete-confirm modal seeds
      // its checkbox from this same collection's delete_media_override, and
      // without this it can read stale data if the user navigates back there
      // shortly after toggling the item-level checkbox here. This hook is
      // Game-only (hardcodes /api/v1/game-item-bundle/ below), so the list
      // key matches EntityListPage's invalidate() for gameDomainConfig
      // (['game', 'list', ...]), was ['library'], the pre-cutover Games.tsx
      // list query key, dead since Games.tsx moved onto EntityListPage.
      queryClient.invalidateQueries({ queryKey: ['game', 'list'] });
    },
  });
  const deleteMediaOverrideError = deleteMediaOverrideMutation.isError
    ? deleteMediaOverrideMutation.error instanceof ApiError
      ? deleteMediaOverrideMutation.error.detail
      : 'Failed to update.'
    : null;

  const {
    confirm: confirmDelete,
    isOpen: deleteConfirmOpen,
    options: deleteConfirmOptions,
    handleConfirm: handleDeleteConfirm,
    handleCancel: handleDeleteCancel,
    getCheckboxValue: getDeleteCheckboxValue,
  } = useConfirm();
  const { issue: issueDeleteToken, consume: consumeDeleteToken } = useConfirmToken();
  const withRatingChangeConfirm = useRatingChangeConfirm(confirmDelete);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete() {
    if (collectionId == null || title == null) return;
    const confirmed = await confirmDelete({
      title: `Delete "${title}"?`,
      consequence: 'This removes the game from your library.',
      destructive: true,
      checkbox: { label: 'Also delete media files from disk', defaultChecked: resolvedDeleteMedia },
    });
    if (!confirmed) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      // See the module comment above: sent on every attempt, never PATCHed.
      const checkedDeleteMedia = getDeleteCheckboxValue();
      // A fresh token per attempt: the rating-change prompt can outlast the
      // token's 60s TTL.
      const completed = await withRatingChangeConfirm(async (confirmRatingChange) => {
        const token = await issueDeleteToken(
          `/api/v1/game-item-bundle/${collectionId}/confirm-delete`,
        );
        await consumeDeleteToken(`/api/v1/game-item-bundle/${collectionId}`, token, {
          confirmRatingChange,
          deleteMedia: checkedDeleteMedia,
          ratingChangeHandled: true,
        });
      });
      if (!completed) {
        setDeleting(false);
        return;
      }
      queryClient.invalidateQueries({ queryKey: ['game', 'list'] });
      onDeleted();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.detail : 'Delete failed.');
      setDeleting(false);
    }
  }

  return {
    deleteMediaOverrideMutate: deleteMediaOverrideMutation.mutate,
    deleteMediaOverrideError,
    deleteConfirmOpen,
    deleteConfirmOptions,
    handleDeleteConfirm,
    handleDeleteCancel,
    deleting,
    deleteError,
    handleDelete,
  };
}
