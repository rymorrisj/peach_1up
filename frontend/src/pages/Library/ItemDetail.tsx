import { useParams, Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import { Button } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import ConfirmModal from '@/components/common/ConfirmModal'
import { useAppContext } from '@/context/AppContext'
import { useLaunch } from '@/hooks/useLaunch'
import { useLibraryItem } from '@/hooks/useLibraryItem'
import { useLibraryItemActions } from '@/hooks/useLibraryItemActions'
import { TagsSection } from './components/TagsSection'
import { EditForm } from './components/EditForm'
import { AdvancedSection } from './components/AdvancedSection'
import { RestrictionsSection } from './components/RestrictionsSection'
import { LaunchHistorySection } from './components/LaunchHistory'
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

  function handleLaunch() {
    if (!item || !actions.form) return
    const profileId = actions.form.profile_id ? parseInt(actions.form.profile_id, 10) : null
    if (!profileId) return
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
    <div className="flex flex-col min-h-full">
      <TopBar title={item.title} />

      <div className="p-6">
        <div className="mb-6">
          <Link to="/library" className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
            ← Library
          </Link>
        </div>

        <div className="max-w-xl space-y-10">

          {/* ── Meta (read-only) ── */}
          <section className="space-y-1 text-sm text-neutral-600 dark:text-neutral-300">
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
            <div>
              <span className="font-medium">Era:</span> {eraLabel}
              {item.detection_reason && (
                <span className="ml-1 text-xs text-neutral-400 dark:text-neutral-500 italic">
                  — {item.detection_reason}
                </span>
              )}
            </div>
            {item.launch_count > 0 && (
              <div>
                <span className="font-medium">Launches:</span> {item.launch_count}
                {item.last_launched_at && (
                  <> · Last {new Date(item.last_launched_at).toLocaleDateString()}</>
                )}
              </div>
            )}
            {item.era === 'dos' && (
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
                    {item.drive?.size_mb != null ? `${item.drive.size_mb} MB` : <span className="italic text-neutral-400 dark:text-neutral-500">Drive created on first launch</span>}
                  </span>
                </div>
              </>
            )}
          </section>

          <TagsSection
            item={item}
            isAdminOrOwner={isAdminOrOwner}
            onRemove={actions.handleRemoveTag}
            onAssign={actions.handleAssignTag}
            error={actions.tagError}
          />

          <EditForm
            item={item}
            form={actions.form}
            setField={actions.setField}
            handleSave={actions.handleSave}
            saving={actions.saving}
            saveError={actions.saveError}
            saveSuccess={actions.saveSuccess}
            execBrowserOpen={actions.execBrowserOpen}
            setExecBrowserOpen={actions.setExecBrowserOpen}
            launchCommands={actions.launchCommands}
            setLaunchCommands={actions.setLaunchCommands as (cmds: string[]) => void}
            profiles={profiles}
            platforms={platforms}
          />

          <AdvancedSection
            item={item}
            flagging={actions.flagging}
            flagError={actions.flagError}
            onFlagLaunch={actions.handleFlagLaunch}
            launchCommands={actions.launchCommands}
            setLaunchCommands={actions.setLaunchCommands as (cmds: string[]) => void}
          />

          {/* ── Launch ── */}
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Launch
            </h2>

            <Button
              onClick={handleLaunch}
              loading={launching}
              disabled={!hasProfile || launching}
              className="w-full justify-center py-3 text-base"
            >
              {hasProfile ? 'Launch' : 'Assign a profile to launch'}
            </Button>

            {!hasProfile && (
              <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
                Select a launch profile above to enable launch.
              </p>
            )}

            {launchSuccess && (
              <p className="text-center text-sm text-green-600 dark:text-green-400">
                Launch started. The emulator should open shortly.
              </p>
            )}

            {launchWarnings.map((w, i) => (
              <p key={i} className="text-center text-xs text-amber-600 dark:text-amber-400">
                ⚠ {w}
              </p>
            ))}

            {launchError && (
              <p role="alert" className="text-center text-sm text-red-600 dark:text-red-400">
                ❌ {launchError}
              </p>
            )}
          </section>

          {isAdminOrOwner && (
            <RestrictionsSection
              users={nonOwnerUsers}
              restrictedIds={actions.restrictedIds}
              restrictionsDirty={actions.restrictionsDirty}
              toggleRestriction={actions.toggleRestriction}
              onSave={actions.handleSaveRestrictions}
              saving={actions.savingRestrictions}
              error={actions.restrictionsError}
            />
          )}

          <LaunchHistorySection history={launchHistory} />

        </div>
      </div>

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
    </div>
  )
}
