import { useParams, Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useAppContext } from '@/context/useAppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useLibraryItem } from '@/hooks/useLibraryItem'
import { useLibraryItemActions } from '@/hooks/useLibraryItemActions'
import { LibraryEntityDetail } from './components/LibraryEntityDetail'
import { ERA_LABELS } from '@/generated/constants'

export default function ItemDetail() {
  const { slug } = useParams<{ slug: string }>()
  const queryClient = useQueryClient()
  const { state: appState } = useAppContext()

  const isAdminOrOwner =
    (appState.activeUser?.is_admin ?? false) || (appState.activeUser?.is_owner ?? false)

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
