import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import { useConfirm } from './useConfirm';
import { useConfirmToken } from './useConfirmToken';

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
// delete_media_override is written by two independent paths here: the
// standalone mutation below (fire-and-forget, from the page's own checkbox),
// and an unconditional PATCH inside handleDelete just before issuing the
// confirm token. That second PATCH is intentionally unconditional, not
// gated on whether the confirm dialog's checkbox differs from
// resolvedDeleteMedia (React Query cache), because the cache can still be
// stale if the standalone mutation was toggled moments earlier and hasn't
// round-tripped yet. Writing unconditionally makes handleDelete the single
// source of truth delete_library_collection reads, regardless of cache
// freshness. Keep both writes, don't collapse them into one conditional
// PATCH.
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
      const checkedDeleteMedia = getDeleteCheckboxValue();
      // See the module comment above, this write must stay unconditional.
      await apiFetch(`/api/v1/game-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ delete_media_override: checkedDeleteMedia }),
      });
      const token = await issueDeleteToken(
        `/api/v1/game-item-bundle/${collectionId}/confirm-delete`,
      );
      await consumeDeleteToken(`/api/v1/game-item-bundle/${collectionId}`, token);
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
