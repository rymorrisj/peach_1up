import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useAppContext } from '@/context/useAppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useLibraryItem } from '@/hooks/useLibraryItem'
import { useLibraryItemActions } from '@/hooks/useLibraryItemActions'
import { LibraryEntityDetail } from './components/LibraryEntityDetail'
import { FetchMetadataModal } from './components/FetchMetadataModal'
import { ERA_LABELS } from '@/generated/constants'

export default function ItemDetail() {
  const { slug } = useParams<{ slug: string }>()
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()
  const [fetchMetadataOpen, setFetchMetadataOpen] = useState(false)

  const isAdminOrOwner =
    (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)
  const isOwner = appState.activeUser?.is_owner ?? false

  const { data: apiKeyStatus } = useQuery({
    queryKey: ['thegamesdb-api-key-status'],
    queryFn: () => apiFetch<{ enabled: boolean }>('/api/v1/settings/thegamesdb-api-key/status'),
    enabled: isOwner,
    staleTime: 30_000,
  })
  const theGamesDbEnabled = isOwner && (apiKeyStatus?.enabled !== false)

  const { item, itemLoading, profiles, platforms, users, restrictionsData, refetchRestrictions, launchHistory } =
    useLibraryItem(slug, isAdminOrOwner)

  const actions = useLibraryItemActions({
    item,
    slug,
    isAdminOrOwner,
    restrictionsData,
    refetchRestrictions,
  })

  const {
    launch,
    isLaunching: launching,
    error: launchError,
    launchSuccess,
    launchWarnings,
  } = useLaunch({
    targetId: item?.id ?? 0,
    targetType: 'library',
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['launches', item?.id] })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    },
  })

  async function handleLaunch() {
    if (!item || !actions.form) return
    const profileId = actions.form.profile_id ? parseInt(actions.form.profile_id, 10) : null
    if (!profileId) return
    // Persist profile_id if it hasn't been saved yet, so it survives page reloads.
    if (profileId !== item.profile_id) {
      try {
        await apiFetch(`/api/v1/library/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ profile_id: profileId }),
        })
        queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
      } catch {
        // Save errors shown by server; still launch since profile_id is in the request.
      }
    }
    launch(profileId)
  }

  if (itemLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <LoadingSpinner label="Loading…" />
        <span aria-hidden="true">Loading…</span>
      </div>
    )
  }

  if (!item || !actions.form) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-neutral-500">Library item not found.</p>
        <Link to="/library" className="text-sm text-[#ff8a5c] hover:underline">
          ← Back to Library
        </Link>
      </div>
    )
  }

  const eraLabel = ERA_LABELS[item.era] ?? (item.era === 'unknown' ? 'Unknown' : item.era)
  const effectiveProfileId = actions.form.profile_id ? parseInt(actions.form.profile_id, 10) : null
  const hasProfile = effectiveProfileId != null
  const nonOwnerUsers = users.filter((u) => !u.is_owner)

  const storageKey = `fetch_metadata_${window.location.pathname}`

  return (
    <>
      <LibraryEntityDetail
        title={item.title}
        eraLabel={eraLabel}
        eraDetectionReason={item.detection_reason ?? undefined}
        launchCount={item.launch_count}
        lastLaunchedAt={item.last_launched_at}
        metaBefore={
          <>
            <div className="flex items-start gap-1">
              <span className="font-medium shrink-0">Slug:</span>
              <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400 self-center">
                {item.slug ?? '—'}
              </span>
            </div>
            <div className="flex items-start gap-1">
              <span className="font-medium shrink-0">Path:</span>
              <span className="break-all font-mono text-xs text-neutral-500 dark:text-neutral-400">
                {item.media_path}
              </span>
            </div>
          </>
        }
        metaAfter={
          item.era === 'dos' ? (
            <>
              <div className="flex items-center gap-2">
                <span className="font-medium shrink-0">Installed:</span>
                <span className="text-neutral-500 dark:text-neutral-400">
                  {actions.localInstalled ? '● Yes' : '○ No'}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={actions.handleToggleInstalled}
                  loading={actions.installedMutation.isPending}
                >
                  {actions.localInstalled ? 'Mark as not installed' : 'Mark as installed'}
                </Button>
              </div>
              <div>
                <span className="font-medium">Drive size:</span>{' '}
                <span className="text-neutral-500 dark:text-neutral-400">
                  {item.drive?.size_mb != null
                    ? `${item.drive.size_mb} MB`
                    : <span className="italic text-neutral-400 dark:text-neutral-500">Drive created on first launch</span>}
                </span>
              </div>
            </>
          ) : undefined
        }
        tags={{
          entity: { id: item.id, tags: item.tags ?? [] },
          isAdminOrOwner,
          onRemove: actions.handleRemoveTag,
          onAssign: actions.handleAssignTag,
          error: actions.tagError,
        }}
        editForm={{
          item,
          form: actions.form,
          setField: actions.setField,
          handleSave: actions.handleSave,
          saving: actions.saving,
          saveError: actions.saveError,
          saveSuccess: actions.saveSuccess,
          execBrowserOpen: actions.execBrowserOpen,
          setExecBrowserOpen: actions.setExecBrowserOpen,
          launchCommands: actions.launchCommands,
          setLaunchCommands: actions.setLaunchCommands as (cmds: string[]) => void,
          profiles,
          platforms,
        }}
        advancedSection={{
          item,
          flagging: actions.flagging,
          flagError: actions.flagError,
          onFlagLaunch: actions.handleFlagLaunch,
          launchCommands: actions.launchCommands,
          setLaunchCommands: actions.setLaunchCommands as (cmds: string[]) => void,
        }}
        fetchMetadataAction={
          isOwner ? (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                Metadata
              </h2>
              <div className="flex items-center gap-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setFetchMetadataOpen(true)}
                  disabled={!theGamesDbEnabled}
                  title={!theGamesDbEnabled ? 'TheGamesDB API key not configured — set it in Settings > Metadata' : undefined}
                >
                  Fetch Metadata
                </Button>
                {!theGamesDbEnabled && (
                  <span className="text-xs text-neutral-400">
                    Requires a TheGamesDB API key (Settings &gt; Metadata)
                  </span>
                )}
              </div>
            </section>
          ) : null
        }
        onLaunch={handleLaunch}
        launching={launching}
        launchDisabled={!hasProfile || launching}
        launchButtonLabel={hasProfile ? 'Launch' : 'Assign a profile to launch'}
        launchNote={
          !hasProfile ? (
            <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
              Select a launch profile above to enable launch.
            </p>
          ) : undefined
        }
        launchSuccess={launchSuccess}
        launchWarnings={launchWarnings}
        launchError={launchError}
        restrictions={
          isAdminOrOwner
            ? {
                users: nonOwnerUsers,
                restrictedIds: actions.restrictedIds,
                restrictionsDirty: actions.restrictionsDirty,
                toggleRestriction: actions.toggleRestriction,
                onSave: actions.handleSaveRestrictions,
                saving: actions.savingRestrictions,
                error: actions.restrictionsError,
              }
            : undefined
        }
        launchHistory={launchHistory}
      />

      <FetchMetadataModal
        open={fetchMetadataOpen}
        onClose={() => setFetchMetadataOpen(false)}
        entityType="library_item"
        entityId={item.id}
        entityTitle={item.title}
        storageKey={storageKey}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })}
      />

      <ConfirmModal
        open={actions.installedConfirmOpen}
        title={actions.installedConfirmOptions?.title ?? ''}
        consequence={actions.installedConfirmOptions?.consequence ?? ''}
        destructive={actions.installedConfirmOptions?.destructive}
        onConfirm={actions.handleInstalledConfirm}
        onCancel={actions.handleInstalledCancel}
      />

      {actions.installedMutation.isError && (
        <p role="alert" className="sr-only">
          {actions.installedMutation.error instanceof ApiError
            ? actions.installedMutation.error.detail
            : 'Failed to update.'}
        </p>
      )}
    </>
  )
}
