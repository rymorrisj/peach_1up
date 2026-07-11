import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import EmptyState from '@/components/common/EmptyState'
import { StatusDot, GuidanceNote } from './components/EmulatorDetailPrimitives'
import { CloneRomPackButton } from './components/CloneRomPackButton'
import type { EmulatorStatusData } from '@/pages/FirstRun/types'
import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

function RomPackRow({ entry, isLast }: { entry: CatalogEntry; isLast: boolean }) {
  const queryClient = useQueryClient()
  const [isCloning, setIsCloning] = useState(false)
  const [cloneError, setCloneError] = useState<string | null>(null)

  const { data: cloneStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', entry.slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulators/${entry.slug}/status`),
    refetchInterval: isCloning ? 4000 : false,
    enabled: isCloning,
  })

  useEffect(() => {
    if (!cloneStatus) return
    if (cloneStatus.status === 'complete') {
      setIsCloning(false)
      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
      queryClient.invalidateQueries({ queryKey: ['rom-packs'] })
    }
    if (cloneStatus.status === 'error') {
      setIsCloning(false)
      setCloneError(cloneStatus.error ?? 'Clone failed.')
    }
  }, [cloneStatus])

  async function handleClone() {
    setIsCloning(true)
    setCloneError(null)
    try {
      await apiFetch(`/api/v1/emulators/${entry.slug}/install`, { method: 'POST' })
    } catch (err) {
      setIsCloning(false)
      setCloneError(err instanceof ApiError ? err.detail : 'Failed to start clone.')
    }
  }

  return (
    <div style={{ padding: '14px 18px', borderBottom: isLast ? 'none' : '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
          {entry.name}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
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
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--error)', fontFamily: 'var(--font-display)' }}>
          {cloneError}
        </div>
      )}
    </div>
  )
}

// Cross-emulator ROM pack list — GET /api/v1/emulators/rom-packs returns a
// bare list[RomPackItemRead], not Page[T] (dev_docs/v2/08, Task 4); mounted
// without pagination controls, flagged for the batched backend pass. The
// install/clone action itself is driven off the emulator catalog
// (/api/v1/emulators), same as the per-emulator RomPackTab, since
// CloneRomPackButton and the install/status endpoints are catalog-scoped.
export default function RomPacks() {
  const { data: catalog = [], isLoading } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulators'),
    staleTime: 10_000,
  })

  const romPacks = catalog.filter((e) => e.install_type === 'rom_pack')

  return (
    <div className="p-6">
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg-3)' }}>
          <LoadingSpinner label="Loading ROM packs…" />
          <span aria-hidden="true">Loading ROM packs…</span>
        </div>
      ) : romPacks.length === 0 ? (
        <EmptyState heading="No ROM packs" subtext="No emulators in the catalog require a ROM pack." />
      ) : (
        <div className="rounded-xl" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          {romPacks.map((entry, i) => (
            <RomPackRow key={entry.slug} entry={entry} isLast={i === romPacks.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}
