import type { ComponentProps, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import { RestrictionsSection } from './RestrictionsSection'
import { LaunchHistorySection } from './LaunchHistory'
import { TagsSection } from './TagsSection'
import { EditForm } from './EditForm'
import { AdvancedSection } from './AdvancedSection'
import type { components } from '@shared/types'

type User = components['schemas']['UserRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']

interface RestrictionsProps {
  users: User[]
  restrictedIds: Set<number>
  restrictionsDirty: boolean
  toggleRestriction: (userId: number) => void
  onSave: () => void
  saving: boolean
  error: string | null
}

interface LibraryEntityDetailProps {
  title: string
  eraLabel: string
  eraDetectionReason?: string
  launchCount?: number
  lastLaunchedAt?: string | null
  /** Rendered at the top of the page content, above the Meta section (e.g. the
   * persistent "delete media on removal" checkbox) */
  topControl?: ReactNode
  /** Extra rows inserted before the era row in the meta section (e.g. slug, path) */
  metaBefore?: ReactNode
  /** Extra rows inserted after the launches row in the meta section (e.g. DOS info, disc count) */
  metaAfter?: ReactNode
  /** Tags section props — renders TagsSection when provided */
  tags?: ComponentProps<typeof TagsSection>
  /** Edit form props — renders EditForm when provided */
  editForm?: ComponentProps<typeof EditForm>
  /** Advanced section props — renders AdvancedSection when provided */
  advancedSection?: ComponentProps<typeof AdvancedSection>
  /** Optional action rendered between EditForm and AdvancedSection (e.g. Fetch Metadata button) */
  fetchMetadataAction?: ReactNode
  /** Extra content between the form sections and launch (e.g. disc list for sets) */
  beforeLaunch?: ReactNode
  onLaunch: () => void
  launching: boolean
  launchDisabled?: boolean
  launchButtonLabel?: string
  /** Note rendered directly below the launch button */
  launchNote?: ReactNode
  launchSuccess: boolean
  launchWarnings: string[]
  launchError: string | null
  /** Rendered directly below the launch error (e.g. a "Convert with extract-xiso" action) */
  launchErrorAction?: ReactNode
  /** When provided, renders the Restrictions section after launch */
  restrictions?: RestrictionsProps
  /** Launch session history — renders when non-empty */
  launchHistory?: LaunchHistory[]
}

export function LibraryEntityDetail({
  title,
  eraLabel,
  eraDetectionReason,
  launchCount,
  lastLaunchedAt,
  topControl,
  metaBefore,
  metaAfter,
  tags,
  editForm,
  advancedSection,
  fetchMetadataAction,
  beforeLaunch,
  onLaunch,
  launching,
  launchDisabled,
  launchButtonLabel = 'Launch',
  launchNote,
  launchSuccess,
  launchWarnings,
  launchError,
  launchErrorAction,
  restrictions,
  launchHistory,
}: LibraryEntityDetailProps) {
  return (
    <div className="flex flex-col min-h-full">
      <TopBar title={title} />

      <div className="p-6">
        <div className="mb-6">
          <Link to="/library" className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
            ← Library
          </Link>
        </div>

        <div className="max-w-xl space-y-10">

          {topControl}

          {/* ── Meta (read-only) ── */}
          <section className="space-y-1 text-sm text-neutral-600 dark:text-neutral-300">
            {metaBefore}
            <div>
              <span className="font-medium">Era:</span> {eraLabel}
              {eraDetectionReason && (
                <span className="ml-1 text-xs text-neutral-400 dark:text-neutral-500 italic">
                  — {eraDetectionReason}
                </span>
              )}
            </div>
            {launchCount != null && launchCount > 0 && (
              <div>
                <span className="font-medium">Launches:</span> {launchCount}
                {lastLaunchedAt && (
                  <> · Last {new Date(lastLaunchedAt + 'Z').toLocaleDateString()}</>
                )}
              </div>
            )}
            {metaAfter}
          </section>

          {tags && <TagsSection {...tags} />}

          {editForm && <EditForm {...editForm} />}

          {fetchMetadataAction}

          {advancedSection && <AdvancedSection {...advancedSection} />}

          {beforeLaunch}

          {/* ── Launch ── */}
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Launch
            </h2>

            <Button
              onClick={onLaunch}
              loading={launching}
              disabled={launchDisabled ?? launching}
              className="w-full justify-center py-3 text-base"
            >
              {launchButtonLabel}
            </Button>

            {launchNote}

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

            {launchError && launchErrorAction}
          </section>

          {restrictions && (
            <RestrictionsSection
              users={restrictions.users}
              restrictedIds={restrictions.restrictedIds}
              restrictionsDirty={restrictions.restrictionsDirty}
              toggleRestriction={restrictions.toggleRestriction}
              onSave={restrictions.onSave}
              saving={restrictions.saving}
              error={restrictions.error}
            />
          )}

          <LaunchHistorySection history={launchHistory ?? []} />

        </div>
      </div>
    </div>
  )
}
