import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import { useConfirmToken } from '@/hooks/useConfirmToken'
import { ERA_LABELS } from '@/generated/constants'
import { AddMediaModal } from './components/AddMediaModal'
import { ScanModal } from './components/ScanModal'
import { CollectionCard } from './components/CollectionCard'
import type { LibraryCollectionData } from './components/CollectionCard'

// Server-side pagination envelope (backend models/pagination.py). Typed locally
// so the app builds before @shared/types is regenerated from the OpenAPI spec.
interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

const PAGE_SIZE = 50

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

const SELECT_CLASS =
  'rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[#ff8a5c] border'

interface ResolvedPaths {
  library_path: string | null
  media_path: string | null
}

interface Filters {
  era: string
  profileFilter: 'all' | 'assigned' | 'unassigned'
}

export default function Library() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [addOpen, setAddOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)
  const [filters, setFilters] = useState<Filters>({ era: searchParams.get('era') ?? '', profileFilter: 'all' })
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    setFilters((f) => ({ ...f, era: searchParams.get('era') ?? '' }))
    setOffset(0)
  }, [searchParams])
  const { confirm, isOpen: confirmOpen, options: confirmOptions, handleConfirm, handleCancel } = useConfirm()
  const { issue: issueToken, consume: consumeToken } = useConfirmToken()

  // Filtering is done server-side: the frontend forwards the filter params and
  // the single list response is a paginated Page envelope of collections.
  const listParams = (extra: Record<string, string>) => {
    const params = new URLSearchParams(extra)
    if (filters.era) params.set('era', filters.era)
    if (filters.profileFilter === 'assigned') params.set('profile_assigned', 'true')
    else if (filters.profileFilter === 'unassigned') params.set('profile_assigned', 'false')
    return params.toString()
  }

  const { data: collectionsPage, isLoading } = useQuery<Page<LibraryCollectionData>>({
    queryKey: ['library', filters.era, filters.profileFilter, offset],
    queryFn: () =>
      apiFetch<Page<LibraryCollectionData>>(
        `/api/v1/library?${listParams({ limit: String(PAGE_SIZE), offset: String(offset) })}`,
      ),
    placeholderData: keepPreviousData,
  })
  const collections = collectionsPage?.items ?? []
  const total = collectionsPage?.total ?? 0

  const handleSetDisplayDisk = async (collectionId: number, discId: number) => {
    await apiFetch(`/api/v1/librarycollection/${collectionId}`, {
      method: 'PATCH',
      body: JSON.stringify({ display_disk_id: discId }),
    })
    queryClient.invalidateQueries({ queryKey: ['library'] })
  }

  const { data: settingsData } = useQuery<{ paths: ResolvedPaths }>({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch('/api/v1/settings/first-run-status'),
    staleTime: 60_000,
  })

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['library'] })
  }, [queryClient])

  useEffect(() => {
    window.addEventListener('upload-complete', invalidate)
    return () => window.removeEventListener('upload-complete', invalidate)
  }, [invalidate])

  async function handleRemove(collection: LibraryCollectionData) {
    const confirmed = await confirm({
      title: `Remove "${collection.title}"?`,
      consequence: 'This removes the game from your library. The media file on disk is not deleted.',
      destructive: true,
    })
    if (!confirmed) return
    try {
      const token = await issueToken(`/api/v1/librarycollection/${collection.id}/confirm-delete`)
      await consumeToken(`/api/v1/librarycollection/${collection.id}`, token)
      queryClient.invalidateQueries({ queryKey: ['library'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Remove failed.'
      alert(msg)
    }
  }

  const hasActiveFilters = filters.era !== '' || filters.profileFilter !== 'all'

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Library">
        <span style={{ flex: 1 }} />
        <Button variant="secondary" onClick={() => setScanOpen(true)}>
          Scan Directory
        </Button>
        <Button onClick={() => setAddOpen(true)}>+ Add Media</Button>
      </TopBar>

      <div className="p-6">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg-3)' }}>
            <LoadingSpinner label="Loading library…" />
            <span aria-hidden="true">Loading library…</span>
          </div>
        ) : total === 0 && !hasActiveFilters ? (
          <EmptyState
            heading="Your library is empty"
            subtext="Add media files to get started, or scan a directory to import in bulk."
            cta={{ label: 'Add Media', onClick: () => setAddOpen(true) }}
          />
        ) : (
          <>
            {/* Filter bar */}
            <div className="mb-6 flex flex-wrap items-center gap-3">
              <select
                value={filters.era}
                onChange={(e) => {
                  const v = e.target.value
                  setFilters((f) => ({ ...f, era: v }))
                  setOffset(0)
                  setSearchParams((p) => { if (v) p.set('era', v); else p.delete('era'); return p })
                }}
                className={SELECT_CLASS}
                style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
              >
                <option value="">All eras</option>
                {ERA_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <select
                value={filters.profileFilter}
                onChange={(e) => {
                  setFilters((f) => ({ ...f, profileFilter: e.target.value as Filters['profileFilter'] }))
                  setOffset(0)
                }}
                className={SELECT_CLASS}
                style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
              >
                <option value="all">All games</option>
                <option value="assigned">Profile assigned</option>
                <option value="unassigned">No profile</option>
              </select>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={() => {
                    setFilters({ era: '', profileFilter: 'all' })
                    setOffset(0)
                    setSearchParams((p) => { p.delete('era'); return p })
                  }}
                  style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--fg-3)', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  Clear filters
                </button>
              )}
              <span className="ml-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                {total} game{total === 1 ? '' : 's'}
              </span>
            </div>

            {collections.length === 0 ? (
              <p style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: 'var(--fg-3)' }}>
                No games match the current filters.
              </p>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                {collections.map((c) => (
                  <CollectionCard
                    key={c.id}
                    collection={c}
                    onRemove={handleRemove}
                    onSetDisplayDisk={handleSetDisplayDisk}
                  />
                ))}
              </div>
            )}

            {total > PAGE_SIZE && (
              <div className="mt-6 flex items-center justify-center gap-4">
                <Button
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
                </span>
                <Button
                  variant="secondary"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset((o) => o + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <AddMediaModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdded={invalidate}
        mediaPath={settingsData?.paths?.media_path ?? null}
      />
      <ScanModal
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onImported={invalidate}
        mediaPath={settingsData?.paths?.media_path ?? null}
      />
      <ConfirmModal
        open={confirmOpen}
        title={confirmOptions?.title ?? ''}
        consequence={confirmOptions?.consequence ?? ''}
        destructive={confirmOptions?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  )
}
