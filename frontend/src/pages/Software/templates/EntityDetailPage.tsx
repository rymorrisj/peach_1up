import { useState } from 'react'
import type { ComponentProps } from 'react'
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
type SoftwareEntityDetailProps = ComponentProps<typeof SoftwareEntityDetail>

interface EntityDetailPageProps<TBundle extends EntityBundleBase> {
  config: EntityDomainConfig<TBundle>
}

// Generic detail page: fetch by id (or slug, see config.identifierParam),
// tags, restrictions, and an optional launch button (omitted entirely when
// config.launchTargetType is unset, e.g. Media). Game-only concerns — disc
// reordering, xiso conversion, metadata fetch/enrich, era/profile editing,
// DOS-install — are wired in via config.renderExtras (see
// configs/gameConfig.tsx) rather than hardcoded here, so this shell carries
// no game-specific knowledge. renderExtras is omitted entirely for App/Media,
// so their rendered output is unaffected by its existence.
export function EntityDetailPage<TBundle extends EntityBundleBase>({ config }: EntityDetailPageProps<TBundle>) {
  const params = useParams<{ id?: string; slug?: string }>()
  const usesSlug = config.identifierParam === 'slug'
  const routeIdentifier = usesSlug ? params.slug : params.id
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()
  const isAdminOrOwner = (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)
  const isOwner = appState.activeUser?.is_owner ?? false
  const [tagError, setTagError] = useState<string | null>(null)

  const detailQueryKey = [config.domain, 'detail', routeIdentifier]

  const { data: entity, isLoading } = useQuery<TBundle>({
    queryKey: detailQueryKey,
    queryFn: () => apiFetch<TBundle>(config.bundleApiPath(routeIdentifier as string)),
    enabled: routeIdentifier != null,
  })

  // The numeric id used for everything except the initial fetch (tags,
  // restrictions, launch, and any config.renderExtras hooks). For id-routed
  // domains this is just the route param parsed as a number, exactly as
  // before. For slug-routed domains (Game) it isn't known until the entity
  // itself has loaded.
  const entityId = usesSlug ? entity?.id : (routeIdentifier != null ? Number(routeIdentifier) : undefined)

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/user-items'),
    enabled: isAdminOrOwner,
  })
  const restrictionUsers = config.filterRestrictionUsers ? config.filterRestrictionUsers(users) : users

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

  const {
    launch, isLaunching, error: launchError, errorType: launchErrorType, launchSuccess, launchWarnings,
  } = useLaunch({
    targetId: entityId ?? 0,
    targetType: config.launchTargetType ?? 'collection',
    onSettled: () => queryClient.invalidateQueries({ queryKey: detailQueryKey }),
  })

  // Called unconditionally every render (config is a fixed module-level
  // object per mounted page, so whether renderExtras exists never varies
  // across renders of a given instance) — internally composes whatever
  // domain-specific hooks it needs, exactly like a custom hook.
  const extras = config.renderExtras?.({
    entity,
    entityId,
    detailQueryKey,
    isOwner,
    launch,
    isLaunching,
    launchErrorType,
    refetchEntity: () => apiFetch<TBundle>(config.bundleApiPath(routeIdentifier as string)),
  }) ?? {}

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
          ← {config.backLabel ?? 'Back'}
        </Link>
      </div>
    )
  }

  const hasLaunch = config.launchTargetType != null && (config.isLaunchable?.(entity) ?? true)
  const showDescriptionMeta = config.showDescriptionMeta ?? true

  return (
    <>
    <SoftwareEntityDetail
      title={entity.title}
      eraLabel={extras.eraLabel}
      launchCount={extras.launchCount}
      lastLaunchedAt={extras.lastLaunchedAt}
      topControl={extras.topControl}
      metaBefore={showDescriptionMeta && entity.description ? <p>{entity.description}</p> : undefined}
      metaAfter={extras.metaAfter}
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
      editForm={extras.editForm as SoftwareEntityDetailProps['editForm']}
      advancedSection={extras.advancedSection as SoftwareEntityDetailProps['advancedSection']}
      fetchMetadataAction={extras.fetchMetadataAction}
      beforeLaunch={extras.beforeLaunch}
      onLaunch={hasLaunch ? (extras.onLaunch ?? (() => launch())) : undefined}
      launching={hasLaunch ? isLaunching : undefined}
      launchDisabled={hasLaunch ? extras.launchDisabled : undefined}
      launchButtonLabel={hasLaunch ? extras.launchButtonLabel : undefined}
      launchNote={hasLaunch ? extras.launchNote : undefined}
      launchSuccess={hasLaunch ? launchSuccess : undefined}
      launchWarnings={hasLaunch ? launchWarnings : undefined}
      launchError={hasLaunch ? launchError : undefined}
      launchErrorAction={hasLaunch ? extras.launchErrorAction : undefined}
      restrictions={
        isAdminOrOwner
          ? {
              users: restrictionUsers,
              restrictedIds: restrictions.restrictedIds,
              restrictionsDirty: restrictions.restrictionsDirty,
              toggleRestriction: restrictions.toggleRestriction,
              onSave: restrictions.handleSaveRestrictions,
              saving: restrictions.savingRestrictions,
              error: restrictions.restrictionsError,
            }
          : undefined
      }
      launchHistory={extras.launchHistory as SoftwareEntityDetailProps['launchHistory']}
    />
    {extras.afterContent}
    </>
  )
}
