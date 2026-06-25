import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
import { ItemCard } from './components/ItemCard'
import { SetCard } from './components/SetCard'
import type { LibrarySetData } from './components/SetCard'
import type { components } from '@shared/types'
type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']

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

  useEffect(() => {
    setFilters((f) => ({ ...f, era: searchParams.get('era') ?? '' }))
  }, [searchParams])
  const { confirm, isOpen: confirmOpen, options: confirmOptions, handleConfirm, handleCancel } = useConfirm()
  const { issue: issueToken, consume: consumeToken } = useConfirmToken()

  const { data: items, isLoading: itemsLoading } = useQuery<LibraryItem[]>({
    queryKey: ['library'],
    queryFn: () => apiFetch<LibraryItem[]>('/api/v1/library'),
  })

  const { data: sets = [] } = useQuery<LibrarySetData[]>({
    queryKey: ['library-sets'],
    queryFn: () => apiFetch<LibrarySetData[]>('/api/v1/library/sets'),
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: settingsData } = useQuery<{ paths: ResolvedPaths }>({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch('/api/v1/settings/first-run-status'),
    staleTime: 60_000,
  })

  const filteredItems = (items ?? []).filter((item) => {
    if (filters.era && item.era !== filters.era) return false
    if (filters.profileFilter === 'assigned' && item.profile_id === null) return false
    if (filters.profileFilter === 'unassigned' && item.profile_id !== null) return false
    return true
  })

  const filteredSets = sets.filter((s) => {
    if (filters.era && s.era !== filters.era) return false
    if (filters.profileFilter === 'assigned' && s.profile_id === null) return false
    if (filters.profileFilter === 'unassigned' && s.profile_id !== null) return false
    return true
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['library'] })
    queryClient.invalidateQueries({ queryKey: ['library-sets'] })
  }

  async function handleRemove(item: LibraryItem) {
    const confirmed = await confirm({
      title: `Remove "${item.title}"?`,
      consequence: 'This removes the item from your library. The media file on disk is not deleted.',
      destructive: true,
    })
    if (!confirmed) return
    try {
      const token = await issueToken(`/api/v1/library/${item.id}/confirm-delete`)
      await consumeToken(`/api/v1/library/${item.id}`, token)
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
        {itemsLoading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg-3)' }}>
            <LoadingSpinner label="Loading library…" />
            <span aria-hidden="true">Loading library…</span>
          </div>
        ) : (!items || items.length === 0) && sets.length === 0 ? (
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
                onChange={(e) =>
                  setFilters((f) => ({ ...f, profileFilter: e.target.value as Filters['profileFilter'] }))
                }
                className={SELECT_CLASS}
                style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
              >
                <option value="all">All items</option>
                <option value="assigned">Profile assigned</option>
                <option value="unassigned">No profile</option>
              </select>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={() => {
                    setFilters({ era: '', profileFilter: 'all' })
                    setSearchParams((p) => { p.delete('era'); return p })
                  }}
                  style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--fg-3)', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  Clear filters
                </button>
              )}
              <span className="ml-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                {filteredItems.length + filteredSets.length} of {(items?.length ?? 0) + sets.length}
              </span>
            </div>

            {filteredItems.length === 0 && filteredSets.length === 0 ? (
              <p style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: 'var(--fg-3)' }}>
                No items match the current filters.
              </p>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                {filteredSets.map((s) => (
                  <SetCard key={`set-${s.id}`} set={s} />
                ))}
                {filteredItems.map((item) => (
                  <ItemCard
                    key={item.id}
                    item={item}
                    profiles={profiles}
                    onRemove={handleRemove}
                  />
                ))}
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
