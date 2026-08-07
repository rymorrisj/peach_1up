import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import EmptyState from '@/components/common/EmptyState';
import { Button } from '@/ui';
import { usePaginatedList } from '@/hooks/usePaginatedList';
import { StatusDot, GuidanceNote } from './components/EmulatorDetailPrimitives';
import { CloneRomPackButton } from './components/CloneRomPackButton';
import type { EmulatorStatusData } from '@/pages/FirstRun/types';
import type { components } from '@shared/types';
type CatalogEntry = components['schemas']['CatalogEntryResponse'];
type RomPackItem = components['schemas']['RomPackItemRead'];

function RomPackRow({ entry, isLast }: { entry: CatalogEntry; isLast: boolean }) {
  const queryClient = useQueryClient();
  const [isCloning, setIsCloning] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);

  const { data: cloneStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', entry.slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulator-items/${entry.slug}/status`),
    refetchInterval: isCloning ? 4000 : false,
    enabled: isCloning,
  });

  useEffect(() => {
    if (!cloneStatus) return;
    if (cloneStatus.status === 'complete') {
      setIsCloning(false);
      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
      queryClient.invalidateQueries({
        queryKey: ['paginated-list', '/api/v1/emulator-items/rom-packs'],
      });
    }
    if (cloneStatus.status === 'error') {
      setIsCloning(false);
      setCloneError(cloneStatus.error ?? 'Clone failed.');
    }
  }, [cloneStatus]);

  async function handleClone() {
    setIsCloning(true);
    setCloneError(null);
    try {
      await apiFetch(`/api/v1/emulator-items/${entry.slug}/install`, { method: 'POST' });
    } catch (err) {
      setIsCloning(false);
      setCloneError(err instanceof ApiError ? err.detail : 'Failed to start clone.');
    }
  }

  return (
    <div
      style={{
        padding: '14px 18px',
        borderBottom: isLast ? 'none' : '1px solid rgb(var(--border))',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
          marginBottom: 8,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: '0.875rem',
            color: 'rgb(var(--fg-1))',
          }}
        >
          {entry.name}
        </span>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: 'var(--font-display)',
            fontSize: '0.8125rem',
            color: 'rgb(var(--fg-3))',
          }}
        >
          <StatusDot ok={entry.is_installed} />
          {entry.is_installed ? 'Installed' : 'Not installed'}
        </div>
        <CloneRomPackButton
          romPackEntry={entry}
          isCloning={isCloning}
          cloneError={null}
          onClone={handleClone}
        />
      </div>
      {!entry.is_installed && <GuidanceNote text={entry.guidance_text} url={entry.guidance_url} />}
      {cloneError && (
        <div
          style={{
            marginTop: 8,
            fontSize: '0.75rem',
            color: 'rgb(var(--error))',
            fontFamily: 'var(--font-display)',
          }}
        >
          {cloneError}
        </div>
      )}
    </div>
  );
}

// Cross-emulator ROM pack list, paginated via GET /api/v1/emulator-items/rom-packs
// (Page[RomPackItemRead], dev_docs/v2/08, Task 4). Each paginated slug is
// cross-referenced against the emulator catalog (/api/v1/emulator-items, small and
// unpaginated by design, same source doc 08 P7 uses for the per-emulator
// RomPackTab) to get the live is_installed/guidance fields the reused
// CloneRomPackButton/GuidanceNote components need, the backend derives both
// endpoints from the same catalog, so every paginated slug always resolves.
export default function RomPacks() {
  const {
    items: romPackItems,
    isLoading: isRomPacksLoading,
    page,
    pageCount,
    hasPrevPage,
    hasNextPage,
    prevPage,
    nextPage,
  } = usePaginatedList<RomPackItem>({ path: '/api/v1/emulator-items/rom-packs' });

  const { data: catalog = [], isLoading: isCatalogLoading } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulator-items'),
    staleTime: 10_000,
  });

  // Both sources must be loaded before rendering, romPacks below depends on
  // cross-referencing the two, so a partial load must not show an empty state.
  const isLoading = isRomPacksLoading || isCatalogLoading;

  const romPacks = romPackItems
    .map((item) => catalog.find((c) => c.slug === item.slug))
    .filter((entry): entry is CatalogEntry => entry !== undefined);

  return (
    <div className="p-6">
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: 'rgb(var(--fg-3))' }}>
          <LoadingSpinner label="Loading ROM packs…" />
          <span aria-hidden="true">Loading ROM packs…</span>
        </div>
      ) : romPacks.length === 0 ? (
        <EmptyState
          heading="No ROM packs"
          subtext="No emulators in the catalog require a ROM pack."
        />
      ) : (
        <>
          <div
            className="rounded-xl"
            style={{ background: 'rgb(var(--surface-1))', border: '1px solid rgb(var(--border))' }}
          >
            {romPacks.map((entry, i) => (
              <RomPackRow key={entry.slug} entry={entry} isLast={i === romPacks.length - 1} />
            ))}
          </div>
          {pageCount > 1 && (
            <div className="mt-4 flex items-center justify-between gap-4">
              <Button variant="secondary" size="sm" onClick={prevPage} disabled={!hasPrevPage}>
                Previous
              </Button>
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                Page {page} of {pageCount}
              </span>
              <Button variant="secondary" size="sm" onClick={nextPage} disabled={!hasNextPage}>
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
