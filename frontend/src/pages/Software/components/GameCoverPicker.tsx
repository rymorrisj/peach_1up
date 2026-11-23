import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { ImageIcon } from 'lucide-react';
import { apiFetch, ApiError } from '@/api/client';
import { Button } from '@/ui';
import { CoverImage } from './CoverImage';

// Image files from the media linked to this game, as the backend lists them
// for this caller (GET /game-item-bundle/{id}/cover-candidates). Hidden media
// is never in the list, and the server re-checks on set.
export interface CoverCandidate {
  media_item_id: number;
  title: string;
  asset_type: string | null;
  file_url: string;
  media_item_bundle_id: number | null;
  is_current: boolean;
}

interface GameCoverPickerProps {
  bundleId: number;
  // The disc whose cover the card shows (effective display disc), and
  // whether it has one, so Clear only shows when there is something to clear.
  displayDiscId: number | null;
  hasCover: boolean;
  detailQueryKey: QueryKey;
  // Called with the new stored path, or null once cleared, so the edit form's
  // own cover field follows without discarding other unsaved edits.
  onCoverChanged: (path: string | null) => void;
}

function candidatesQueryKey(bundleId: number): QueryKey {
  return ['game', 'cover-candidates', bundleId];
}

export function GameCoverPicker({
  bundleId,
  displayDiscId,
  hasCover,
  detailQueryKey,
  onCoverChanged,
}: GameCoverPickerProps) {
  const queryClient = useQueryClient();

  const { data: candidates = [] } = useQuery<CoverCandidate[]>({
    queryKey: candidatesQueryKey(bundleId),
    queryFn: () =>
      apiFetch<CoverCandidate[]>(`/api/v1/game-item-bundle/${bundleId}/cover-candidates`),
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: detailQueryKey });
    queryClient.invalidateQueries({ queryKey: candidatesQueryKey(bundleId) });
    queryClient.invalidateQueries({ queryKey: ['game', 'list'] });
  }

  const setMutation = useMutation<{ cover_art_path: string | null }, Error, number>({
    mutationFn: (mediaItemId) =>
      apiFetch(`/api/v1/game-item-bundle/${bundleId}/cover-art`, {
        method: 'PUT',
        body: JSON.stringify({ media_item_id: mediaItemId }),
      }),
    onSuccess: (leaf) => {
      onCoverChanged(leaf.cover_art_path);
      refresh();
    },
  });

  const clearMutation = useMutation<unknown, Error, void>({
    mutationFn: () =>
      apiFetch(`/api/v1/game-item-bundle/${bundleId}/items/${displayDiscId}`, {
        method: 'PATCH',
        body: JSON.stringify({ cover_art_path: null }),
      }),
    onSuccess: () => {
      onCoverChanged(null);
      refresh();
    },
  });

  if (candidates.length === 0) return null;

  const busy = setMutation.isPending || clearMutation.isPending;
  const failure = setMutation.error ?? clearMutation.error;
  const errorText = failure
    ? failure instanceof ApiError
      ? failure.detail
      : 'Failed to update cover art.'
    : null;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
          Cover art from linked media
        </h2>
        {hasCover && displayDiscId != null && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => {
              setMutation.reset();
              clearMutation.mutate();
            }}
          >
            Clear cover
          </Button>
        )}
      </div>
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(7rem,1fr))] gap-3">
        {candidates.map((c) => (
          <li key={c.media_item_id} className="flex min-w-0 flex-col gap-1.5 text-sm">
            <button
              type="button"
              aria-label={`Use ${c.title} as cover art`}
              aria-pressed={c.is_current}
              disabled={busy || c.is_current}
              onClick={() => {
                clearMutation.reset();
                setMutation.mutate(c.media_item_id);
              }}
              className={`aspect-square overflow-hidden rounded-md border bg-neutral-100 transition-opacity hover:opacity-90 disabled:cursor-default dark:bg-neutral-800 ${
                c.is_current
                  ? 'border-peach ring-2 ring-peach'
                  : 'border-neutral-200 dark:border-neutral-700'
              }`}
            >
              <CoverImage
                src={c.file_url}
                alt=""
                className="h-full w-full object-cover"
                fallback={
                  <span className="flex h-full w-full items-center justify-center text-neutral-400 dark:text-neutral-500">
                    <ImageIcon className="h-8 w-8" aria-hidden="true" />
                  </span>
                }
              />
            </button>
            <span title={c.title} className="truncate text-neutral-700 dark:text-neutral-200">
              {c.title}
            </span>
            {c.is_current && (
              <span className="text-xs text-neutral-400 dark:text-neutral-500">Cover art</span>
            )}
          </li>
        ))}
      </ul>
      {errorText && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {errorText}
        </p>
      )}
    </section>
  );
}
