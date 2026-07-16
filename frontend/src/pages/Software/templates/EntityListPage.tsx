import { useState } from 'react'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import { EntityCard } from '../components/EntityCard'
import { LibraryModal } from '../components/LibraryModal'
import type { EntityBundleBase, EntityDomainConfig, Page } from '../types'

const PAGE_SIZE = 50

interface SoftwarePaths {
  library_path: string | null
  software_path: string | null
  media_path: string | null
}

interface EntityListPageProps<TBundle extends EntityBundleBase> {
  config: EntityDomainConfig<TBundle>
}

// Generic paginated grid page for domains that don't need Game's era/profile
// filter bar. Add-content is opt-in per domain via config.uploadConfig, Media
// and Apps supply one (via mediaConfig.tsx/appConfig.tsx), rendering a
// "+ Add {label}" button and the shared LibraryModal; a domain that omits it
// renders no add affordance at all.
export function EntityListPage<TBundle extends EntityBundleBase>({ config }: EntityListPageProps<TBundle>) {
  const queryClient = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const {
    confirm, isOpen: confirmOpen, options: confirmOptions, handleConfirm, handleCancel,
  } = useConfirm()

  const { data: page, isLoading } = useQuery<Page<TBundle>>({
    queryKey: [config.domain, 'list', offset],
    queryFn: () => apiFetch<Page<TBundle>>(`${config.listApiPath}?limit=${PAGE_SIZE}&offset=${offset}`),
    placeholderData: keepPreviousData,
  })
  const entities = page?.items ?? []
  const total = page?.total ?? 0

  // Only fetched for domains that actually render the upload modal, avoids
  // an extra settings round-trip for domains with no uploadConfig.
  const { data: settingsData } = useQuery<{ paths: SoftwarePaths }>({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch('/api/v1/settings/first-run-status'),
    staleTime: 60_000,
    enabled: Boolean(config.uploadConfig),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: [config.domain, 'list'] })

  async function handleRemove(entity: TBundle) {
    const confirmed = await confirm({
      title: `Remove "${entity.title}"?`,
      consequence: `This removes the ${config.entityLabel} from your library.`,
      destructive: true,
    })
    if (!confirmed) return
    try {
      await apiFetch(config.bundleApiPath(String(entity.id)), { method: 'DELETE' })
      invalidate()
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Remove failed.')
    }
  }

  const addButtonLabel = `+ Add ${config.entityLabel}`

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        {config.uploadConfig && (
          <>
            <span style={{ flex: 1 }} />
            <Button onClick={() => setAddOpen(true)}>{addButtonLabel}</Button>
          </>
        )}
      </TopBar>

      <div className="p-6">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg-3)' }}>
            <LoadingSpinner label={`Loading ${config.entityLabelPlural}…`} />
            <span aria-hidden="true">Loading {config.entityLabelPlural}…</span>
          </div>
        ) : total === 0 ? (
          <EmptyState
            heading={`No ${config.entityLabelPlural} yet`}
            subtext={`Nothing in your ${config.entityLabelPlural} library yet.`}
            cta={config.uploadConfig ? { label: addButtonLabel, onClick: () => setAddOpen(true) } : undefined}
          />
        ) : (
          <>
            <div className="mb-6 flex items-center">
              <span className="ml-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                {total} {total === 1 ? config.entityLabel : config.entityLabelPlural}
              </span>
            </div>

            <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
              {entities.map((entity) => (
                <EntityCard
                  key={entity.id}
                  entity={entity}
                  routeBase={config.routeBase}
                  coverArt={config.coverArt}
                  onRemove={handleRemove}
                />
              ))}
            </div>

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

      {config.uploadConfig && (
        <LibraryModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          onComplete={invalidate}
          mediaPath={settingsData?.paths?.media_path ?? settingsData?.paths?.software_path ?? null}
          config={config.uploadConfig}
        />
      )}

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
