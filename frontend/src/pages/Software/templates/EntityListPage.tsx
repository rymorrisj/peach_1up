import { Fragment, useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, Select } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import { useConfirmToken } from '@/hooks/useConfirmToken'
import { ERA_LABELS } from '@/generated/constants'
import { EntityCard } from '../components/EntityCard'
import { LibraryModal } from '../components/LibraryModal'
import type { EntityBundleBase, EntityDomainConfig, Page, TagRead } from '../types'

const PAGE_SIZE = 50

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

interface SoftwarePaths {
  library_path: string | null
  software_path: string | null
  media_path: string | null
}

// Only 'era' is URL-synced (mirrors Games.tsx's Filters.era ↔ ?era= param);
// profileFilter, tagFilter, and sort are in-memory only, same as Games.tsx.
interface ListFilters {
  era: string
  profileFilter: 'all' | 'assigned' | 'unassigned'
  tagFilter: string
  sort: string
}

interface EntityListPageProps<TBundle extends EntityBundleBase> {
  config: EntityDomainConfig<TBundle>
}

// Generic paginated grid page. Add-content, Scan, the era/profile filter bar,
// sort control, multi-disc display-disk selection, and the delete-media-override/
// confirm-token delete flow are all opt-in per domain via config
// (uploadConfig/scanConfig/filters/sortOptions/multiDisc/deleteConfig
// respectively), a domain that supplies none of them renders and behaves
// exactly as this page did before those fields existed. Media and Apps supply
// uploadConfig only (via mediaConfig.tsx/appConfig.tsx), so none of the new
// branches below change what they render.
export function EntityListPage<TBundle extends EntityBundleBase>({ config }: EntityListPageProps<TBundle>) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [offset, setOffset] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)
  const [filters, setFilters] = useState<ListFilters>({
    era: config.filters?.era ? (searchParams.get('era') ?? '') : '',
    profileFilter: 'all',
    tagFilter: '',
    sort: '',
  })
  const {
    confirm, isOpen: confirmOpen, options: confirmOptions, handleConfirm, handleCancel, getCheckboxValue,
  } = useConfirm()
  const { issue: issueToken, consume: consumeToken } = useConfirmToken()

  // Only re-syncs from the URL for domains that opt into the era filter, so
  // this effect is a no-op (never touches state) for every other domain.
  useEffect(() => {
    if (!config.filters?.era) return
    setFilters((f) => ({ ...f, era: searchParams.get('era') ?? '' }))
    setOffset(0)
  }, [searchParams, config.filters?.era])

  // Filtering is server-side: only params a domain's config opts into are
  // ever forwarded, so a domain with no `filters` config sends exactly the
  // same request it always did (limit/offset only).
  const listParams = (extra: Record<string, string>) => {
    const params = new URLSearchParams(extra)
    if (config.filters?.era && filters.era) params.set('era', filters.era)
    if (config.filters?.profileAssigned) {
      if (filters.profileFilter === 'assigned') params.set('profile_assigned', 'true')
      else if (filters.profileFilter === 'unassigned') params.set('profile_assigned', 'false')
    }
    if (config.filters?.tag && filters.tagFilter) params.set('tag', filters.tagFilter)
    if (config.sortOptions && filters.sort) params.set('sort', filters.sort)
    return params.toString()
  }

  const { data: page, isLoading } = useQuery<Page<TBundle>>({
    queryKey: [config.domain, 'list', offset, filters.era, filters.profileFilter, filters.tagFilter, filters.sort],
    queryFn: () =>
      apiFetch<Page<TBundle>>(
        `${config.listApiPath}?${listParams({ limit: String(PAGE_SIZE), offset: String(offset) })}`,
      ),
    placeholderData: keepPreviousData,
  })
  const entities = page?.items ?? []
  const total = page?.total ?? 0

  // Same tag list source TagsSection/TagCombobox use for assignment
  // (GET /api/v1/tags, TagRead[] with is_system/item_count). Unlike
  // TagCombobox, system tags are not excluded here: filtering by a
  // system-assigned tag is a valid read, only *assignment* of system tags is
  // blocked (backend 403s that, not filtering). Only fetched for domains that
  // opt into the tag filter, same avoid-extra-round-trip pattern as
  // settingsData/libraryDefaults above.
  const { data: allTags = [] } = useQuery<TagRead[]>({
    queryKey: ['tags'],
    queryFn: () => apiFetch<TagRead[]>('/api/v1/tags'),
    enabled: Boolean(config.filters?.tag),
  })
  const tagOptions = [...allTags].sort((a, b) => a.name.localeCompare(b.name))

  // Only fetched for domains that actually render the upload/scan modal,
  // avoids an extra settings round-trip for domains with neither.
  const { data: settingsData } = useQuery<{ paths: SoftwarePaths }>({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch('/api/v1/settings/first-run-status'),
    staleTime: 60_000,
    enabled: Boolean(config.uploadConfig || config.scanConfig),
  })

  // Only fetched for domains that opt into the delete-media-override flow
  // (deleteConfig), same avoid-extra-round-trip pattern as settingsData above.
  const { data: libraryDefaults } = useQuery<{ delete_media_on_removal: boolean; delete_original_on_upload: boolean }>({
    queryKey: ['settings', 'library-defaults'],
    queryFn: () => apiFetch('/api/v1/settings/library-defaults'),
    staleTime: 60_000,
    enabled: Boolean(config.deleteConfig),
  })
  const deleteMediaOnRemoval = Boolean(libraryDefaults?.delete_media_on_removal)

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: [config.domain, 'list'] })
  }, [queryClient, config.domain])

  // Mirrors Games.tsx's global upload-complete listener. Some upload paths
  // (background/job-based finalize) complete outside this component's own
  // onComplete callbacks, so the list must also invalidate on the global event.
  useEffect(() => {
    window.addEventListener('upload-complete', invalidate)
    return () => window.removeEventListener('upload-complete', invalidate)
  }, [invalidate])

  async function handleSetDisplayDisk(entityId: number, discId: number) {
    if (!config.multiDisc) return
    await config.multiDisc.onSetDisplayDisk(entityId, discId)
    invalidate()
  }

  async function handleRemove(entity: TBundle) {
    const deleteConfig = config.deleteConfig
    // No deleteConfig: original plain confirm+DELETE behavior, unchanged.
    // This remains Media's path today, its backend has neither a
    // confirmation-token contract nor a delete_media_override field.
    if (!deleteConfig) {
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
      return
    }

    // deleteConfig present: Game/App's two-step confirm-token flow, ported
    // from Games.tsx's handleRemove.
    const resolvedDeleteMedia = deleteConfig.resolveDeleteMediaOverride(entity) ?? deleteMediaOnRemoval
    const confirmed = await confirm({
      title: `Remove "${entity.title}"?`,
      consequence: `This removes the ${config.entityLabel} from your library.`,
      destructive: true,
      checkbox: { label: 'Also delete media files from disk', defaultChecked: resolvedDeleteMedia },
    })
    if (!confirmed) return
    try {
      const base = deleteConfig.bundleByIdApiPath(entity.id)
      const checkedDeleteMedia = getCheckboxValue()
      if (checkedDeleteMedia !== resolvedDeleteMedia) {
        await apiFetch(base, {
          method: 'PATCH',
          body: JSON.stringify({ delete_media_override: checkedDeleteMedia }),
        })
      }
      const token = await issueToken(`${base}/confirm-delete`)
      await consumeToken(base, token)
      invalidate()
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Remove failed.')
    }
  }

  const addButtonLabel = `+ Add ${config.entityLabel}`
  const hasActiveFilters = Boolean(config.filters) &&
    (filters.era !== '' || filters.profileFilter !== 'all' || filters.tagFilter !== '')

  // MEDIA_PATH and SOFTWARE_PATH are independently configurable backend
  // settings (see backend/api/routes/settings.py), not one derived from the
  // other. Game/App uploads always target SOFTWARE_PATH (Games.tsx's
  // pre-cutover behavior used software_path only, never media_path), while
  // Media's own uploads target MEDIA_PATH. Picking media_path first
  // unconditionally would silently redirect Game/App uploads to the wrong
  // directory whenever both settings are configured to different paths.
  const resolvedMediaPath = config.domain === 'media'
    ? (settingsData?.paths?.media_path ?? settingsData?.paths?.software_path ?? null)
    : (settingsData?.paths?.software_path ?? settingsData?.paths?.media_path ?? null)

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        {(config.uploadConfig || config.scanConfig) && <span style={{ flex: 1 }} />}
        {config.scanConfig && (
          <Button variant="secondary" onClick={() => setScanOpen(true)}>
            Scan Directory
          </Button>
        )}
        {config.uploadConfig && <Button onClick={() => setAddOpen(true)}>{addButtonLabel}</Button>}
      </TopBar>

      <div className="p-6">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'rgb(var(--fg-3))' }}>
            <LoadingSpinner label={`Loading ${config.entityLabelPlural}…`} />
            <span aria-hidden="true">Loading {config.entityLabelPlural}…</span>
          </div>
        ) : total === 0 && !hasActiveFilters ? (
          <EmptyState
            heading={`No ${config.entityLabelPlural} yet`}
            subtext={`Nothing in your ${config.entityLabelPlural} library yet.`}
            cta={config.uploadConfig ? { label: addButtonLabel, onClick: () => setAddOpen(true) } : undefined}
          />
        ) : (
          <>
            {(config.filters || config.sortOptions) ? (
              <div className="mb-6 flex flex-wrap items-center gap-3">
                {config.filters?.era && (
                  <Select
                    value={filters.era || 'all'}
                    onValueChange={(v) => {
                      const val = v === 'all' ? '' : v
                      setFilters((f) => ({ ...f, era: val }))
                      setOffset(0)
                      setSearchParams((p) => { if (val) p.set('era', val); else p.delete('era'); return p })
                    }}
                    className="w-auto"
                    options={[{ value: 'all', label: 'All eras' }, ...ERA_OPTIONS]}
                  />
                )}
                {config.filters?.profileAssigned && (
                  <Select
                    value={filters.profileFilter}
                    onValueChange={(v) => {
                      setFilters((f) => ({ ...f, profileFilter: v as ListFilters['profileFilter'] }))
                      setOffset(0)
                    }}
                    className="w-auto"
                    options={[
                      { value: 'all', label: `All ${config.entityLabelPlural}` },
                      { value: 'assigned', label: 'Profile assigned' },
                      { value: 'unassigned', label: 'No profile' },
                    ]}
                  />
                )}
                {config.filters?.tag && (
                  <Select
                    value={filters.tagFilter || '__all_tags__'}
                    onValueChange={(v) => {
                      setFilters((f) => ({ ...f, tagFilter: v === '__all_tags__' ? '' : v }))
                      setOffset(0)
                    }}
                    className="w-auto"
                    options={[
                      { value: '__all_tags__', label: 'All tags' },
                      ...tagOptions.map((t) => ({ value: t.name, label: t.name })),
                    ]}
                  />
                )}
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={() => {
                      setFilters((f) => ({ era: '', profileFilter: 'all', tagFilter: '', sort: f.sort }))
                      setOffset(0)
                      setSearchParams((p) => { p.delete('era'); return p })
                    }}
                    style={{ fontFamily: 'var(--font-display)', fontSize: '0.75rem', color: 'rgb(var(--fg-3))', background: 'none', border: 'none', cursor: 'pointer' }}
                  >
                    Clear filters
                  </button>
                )}
                {config.sortOptions && (
                  <Select
                    value={filters.sort || 'default'}
                    onValueChange={(v) => {
                      setFilters((f) => ({ ...f, sort: v === 'default' ? '' : v }))
                      setOffset(0)
                    }}
                    className="w-auto"
                    options={[
                      { value: 'default', label: 'Default order' },
                      ...config.sortOptions.map((o) => ({ value: o.value, label: o.label })),
                    ]}
                  />
                )}
                <span className="ml-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'rgb(var(--fg-3))' }}>
                  {total} {total === 1 ? config.entityLabel : config.entityLabelPlural}
                </span>
              </div>
            ) : (
              <div className="mb-6 flex items-center">
                <span className="ml-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'rgb(var(--fg-3))' }}>
                  {total} {total === 1 ? config.entityLabel : config.entityLabelPlural}
                </span>
              </div>
            )}

            {config.filters && entities.length === 0 ? (
              <p style={{ fontFamily: 'var(--font-display)', fontSize: '0.875rem', color: 'rgb(var(--fg-3))' }}>
                No {config.entityLabelPlural} match the current filters.
              </p>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                {entities.map((entity) => {
                  // renderCard takes over the whole card for domains whose visual
                  // departs from EntityCard's generic layout (Game's stacked-disc
                  // CollectionCard) — wrapped in a keyed Fragment rather than a div
                  // so it stays a direct grid child, matching EntityCard below.
                  if (config.renderCard) {
                    return (
                      <Fragment key={entity.id}>
                        {config.renderCard({
                          entity,
                          onRemove: handleRemove,
                          onSetDisplayDisk: config.multiDisc ? handleSetDisplayDisk : undefined,
                        })}
                      </Fragment>
                    )
                  }
                  const discs = config.multiDisc?.items(entity) ?? []
                  return (
                    <EntityCard
                      key={entity.id}
                      entity={entity}
                      routeBase={config.routeBase}
                      coverArt={config.coverArt}
                      onRemove={handleRemove}
                      multiDisc={
                        config.multiDisc && discs.length > 1
                          ? {
                              discs,
                              displayDiskId: config.multiDisc.displayDiskId(entity),
                              launchDiskId: config.multiDisc.launchDiskId(entity),
                              onSetDisplayDisk: (discId: number) => handleSetDisplayDisk(entity.id, discId),
                            }
                          : undefined
                      }
                    />
                  )
                })}
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
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'rgb(var(--fg-3))' }}>
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
          mediaPath={resolvedMediaPath}
          config={config.uploadConfig}
        />
      )}

      {config.scanConfig && (
        <LibraryModal
          open={scanOpen}
          onClose={() => setScanOpen(false)}
          onComplete={invalidate}
          mediaPath={resolvedMediaPath}
          config={config.scanConfig}
        />
      )}

      <ConfirmModal
        open={confirmOpen}
        title={confirmOptions?.title ?? ''}
        consequence={confirmOptions?.consequence ?? ''}
        destructive={confirmOptions?.destructive}
        checkbox={confirmOptions?.checkbox}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  )
}
