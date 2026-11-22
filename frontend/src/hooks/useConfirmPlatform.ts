import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';

interface UseConfirmPlatformOptions {
  collectionId: number | undefined;
  detailQueryKey: unknown[];
}

// The "Confirm platform" action: PATCHes platform_confirmed true and nothing else,
// then refetches the bundle through the same detail query every other field
// reads. The mutation stays pending until that refetch lands, so the button
// cannot flicker back before platform_review has updated.
export function useConfirmPlatform({ collectionId, detailQueryKey }: UseConfirmPlatformOptions) {
  const queryClient = useQueryClient();

  const mutation = useMutation<unknown, Error, void>({
    mutationFn: async () => {
      if (collectionId == null) throw new Error('No game selected.');
      return apiFetch(`/api/v1/game-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ platform_confirmed: true }),
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: detailQueryKey }),
  });

  const confirmError = mutation.isError
    ? mutation.error instanceof ApiError
      ? mutation.error.detail
      : 'Failed to confirm the platform.'
    : null;

  return {
    confirmPlatform: () => mutation.mutate(),
    confirmingPlatform: mutation.isPending,
    confirmPlatformError: confirmError,
  };
}
