import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useAppContext } from '@/context/useAppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useCollectionRestrictions } from '@/hooks/useCollectionRestrictions'
import { SoftwareEntityDetail } from '../components/SoftwareEntityDetail'
import type { EntityBundleBase, EntityDomainConfig } from '../types'
import type { components } from '@shared/types'

type User = components['schemas']['UserItemRead']

interface EntityDetailPageProps<TBundle extends EntityBundleBase> {
  config: EntityDomainConfig<TBundle>
}

// Generic detail page: fetch by id, tags, restrictions, and an optional
// launch button (omitted entirely when config.launchTargetType is unset,
// e.g. Media). Game-only concerns — disc reordering, xiso conversion,
// metadata fetch/enrich, era/profile editing — stay in CollectionDetail.tsx
// and are not part of this generic shell.
export function EntityDetailPage<TBundle extends EntityBundleBase>({ config }: EntityDetailPageProps<TBundle>) {
  const { id } = useParams<{ id: string }>()
  const entityId = id ? Number(id) : undefined
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()
  const isAdminOrOwner = (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)
  const [tagError, setTagError] = useState<string | null>(null)

  const detailQueryKey = [config.domain, 'detail', entityId]

  const { data: entity, isLoading } = useQuery<TBundle>({
    queryKey: detailQueryKey,
    queryFn: () => apiFetch<TBundle>(config.bundleApiPath(entityId as number)),
    enabled: entityId != null,
  })

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/user-items'),
    enabled: isAdminOrOwner,
  })

  const { data: restrictionsData, refetch: refetchRestrictions } = useQuery<{
    restricted_user_item_ids: number[]
  }>({
    queryKey: ['restrictions', config.domain, entityId],
    queryFn: () =>
      apiFetch<{ restricted_user_item_ids: number[] }>(`/api/v1/restrictions/${config.domain}/${entityId}`),
    enabled: isAdminOrOwner && entityId != null,
  })

  const restrictions = useCollectionRestrictions({
    domain: config.domain,
    collectionId: entityId,
    isAdminOrOwner,
    restrictionsData,
    refetchRestrictions,
  })

  const { launch, isLaunching, error: launchError, launchSuccess, launchWarnings } = useLaunch({
    targetId: entityId ?? 0,
    targetType: config.launchTargetType ?? 'collection',
    onSettled: () => queryClient.invalidateQueries({ queryKey: detailQueryKey }),
  })

  async function handleAssignTag(tagId: number) {
    if (entityId == null) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ entity_type: config.tagEntityType, entity_id: entityId }),
      })
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to add tag.')
    }
  }

  async function handleRemoveTag(tagId: number) {
    if (entityId == null) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/assignments`, {
        method: 'DELETE',
        body: JSON.stringify({ entity_type: config.tagEntityType, entity_id: entityId }),
      })
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to remove tag.')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm" style={{ color: 'var(--fg-3)' }}>
        <LoadingSpinner label={`Loading ${config.entityLabel}…`} />
        <span aria-hidden="true">Loading {config.entityLabel}…</span>
      </div>
    )
  }

  if (!entity) {
    return (
      <div className="p-6">
        <p className="mb-2 text-sm text-neutral-500">
          {config.entityLabel[0].toUpperCase() + config.entityLabel.slice(1)} not found.
        </p>
        <Link to={config.routeBase} className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
          ← Back
        </Link>
      </div>
    )
  }

  const hasLaunch = config.launchTargetType != null && (config.isLaunchable?.(entity) ?? true)

  return (
    <SoftwareEntityDetail
      title={entity.title}
      metaBefore={entity.description ? <p>{entity.description}</p> : undefined}
      tags={
        isAdminOrOwner || entity.tags.length > 0
          ? {
              entity: { id: entity.id, tags: entity.tags },
              isAdminOrOwner,
              onRemove: handleRemoveTag,
              onAssign: handleAssignTag,
              error: tagError,
            }
          : undefined
      }
      onLaunch={hasLaunch ? () => launch() : undefined}
      launching={hasLaunch ? isLaunching : undefined}
      launchSuccess={hasLaunch ? launchSuccess : undefined}
      launchWarnings={hasLaunch ? launchWarnings : undefined}
      launchError={hasLaunch ? launchError : undefined}
      restrictions={
        isAdminOrOwner
          ? {
              users,
              restrictedIds: restrictions.restrictedIds,
              restrictionsDirty: restrictions.restrictionsDirty,
              toggleRestriction: restrictions.toggleRestriction,
              onSave: restrictions.handleSaveRestrictions,
              saving: restrictions.savingRestrictions,
              error: restrictions.restrictionsError,
            }
          : undefined
      }
    />
  )
}
