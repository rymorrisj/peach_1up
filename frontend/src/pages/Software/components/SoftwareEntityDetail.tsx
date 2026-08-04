import type { ComponentProps, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'
import { Card } from '@/ui'
import { ERA_LABEL, ERA_COLOR, ERA_PLACEHOLDER, ERA_PLACEHOLDER_DEFAULT } from '@/types/era'
import { RestrictionsSection } from './RestrictionsSection'
import { LaunchHistorySection } from './LaunchHistory'
import { LaunchSection } from './LaunchSection'
import { TagsSection } from './TagsSection'
import { EditForm } from './EditForm'
import { AdvancedSection } from './AdvancedSection'
import { parseNaiveUtc } from '@/lib/date'
import type { components } from '@shared/types'

type User = components['schemas']['UserItemRead']
type LaunchHistory = components['schemas']['LaunchHistoryRead']

// Local to this file since it has one caller (the Media Size stat below), not
// worth promoting to a shared lib for a single 4-line consumer. Mirrors
// System/Health.tsx's own formatBytes, kept independent rather than shared
// since the two have no other coupling.
function formatBytes(n: number): string {
  if (n >= 1_073_741_824) return `${(n / 1_073_741_824).toFixed(1)} GB`
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(0)} MB`
  if (n >= 1_024) return `${(n / 1_024).toFixed(0)} KB`
  return `${n} B`
}

interface RestrictionsProps {
  users: User[]
  restrictedIds: Set<number>
  restrictionsDirty: boolean
  toggleRestriction: (userId: number) => void
  onSave: () => void
  saving: boolean
  error: string | null
}

interface SoftwareEntityDetailProps {
  title: string
  /** Raw era slug (e.g. "ps1"), omitted entirely for domains with no era
   * concept (Media). Used to render the header's era chip via types/era.ts,
   * the same token/color source the grid cards already use. */
  era?: string
  year?: number | null
  publisher?: string | null
  /** Header thumbnail. Same resolver every grid card already uses
   * (config.coverArt), just not previously threaded into the detail page.
   * Falls back to an era-tinted placeholder (types/era.ts) when null,
   * matching the grid cards' own placeholder treatment. */
  coverArtUrl?: string | null
  launchCount?: number
  lastLaunchedAt?: string | null
  /** At a Glance stat: real backing field (bundle.installed on Game/App),
   * omitted entirely (no tile rendered) when the domain doesn't supply one
   * rather than defaulting to false, so an unwired domain shows no tile
   * instead of a fabricated "No". */
  installedStatus?: boolean
  /** At a Glance stat: summed from real per-item file_size_bytes fields
   * client-side (no bundle-level total exists in the API). Omitted or 0
   * renders no tile — see formatBytes call site for the > 0 gate. */
  mediaSizeBytes?: number | null
  /** Rendered just below the header (e.g. the "delete media on removal"
   * danger-zone block) */
  topControl?: ReactNode
  /** Extra read-only rows inserted before the launches row in the compact
   * meta line (e.g. slug, path) */
  metaBefore?: ReactNode
  /** Extra read-only rows inserted after the launches row (e.g. genre,
   * developer, DOS install toggle) */
  metaAfter?: ReactNode
  /** Tags section props — renders TagsSection when provided */
  tags?: ComponentProps<typeof TagsSection>
  /** Edit form props — renders EditForm when provided. EditForm owns its own
   * internal Profile card and Save button, this slot is not wrapped in an
   * extra card here. */
  editForm?: ComponentProps<typeof EditForm>
  /** Pre-rendered edit form content, for domains whose edit form isn't
   * EditForm (Media, App), rendered in the same slot position as editForm */
  editFormContent?: ReactNode
  /** Advanced section props — renders AdvancedSection when provided */
  advancedSection?: ComponentProps<typeof AdvancedSection>
  /** Metadata actions (Fetch Metadata, Cover Art), rendered inside its own
   * Metadata card */
  fetchMetadataAction?: ReactNode
  /** Extra content between the form sections and launch (e.g. disc list for sets) */
  beforeLaunch?: ReactNode
  /** When omitted, the Launch section doesn't render at all (e.g. Media has no launch capability) */
  onLaunch?: () => void
  launching?: boolean
  launchDisabled?: boolean
  launchButtonLabel?: string
  /** Note rendered directly below the launch button */
  launchNote?: ReactNode
  launchSuccess?: boolean
  launchWarnings?: string[]
  launchError?: string | null
  /** Rendered directly below the launch error (e.g. a "Convert with extract-xiso" action) */
  launchErrorAction?: ReactNode
  /** When provided, renders the Restrictions section after launch */
  restrictions?: RestrictionsProps
  /** Launch session history — renders when non-empty */
  launchHistory?: LaunchHistory[]
  /** Owner/admin only: enables bulk-select + delete on the session history. */
  launchHistoryCanDelete?: boolean
  /** Extra full-width sections rendered after the two-column body, before
   * launch history (e.g. Media's file list, Linked Items). Kept inside this
   * component's own max-w-5xl/space-y-6 flow so it isn't pushed below the
   * min-h-full header/body, which would otherwise leave it stranded past a
   * full viewport of blank space on short pages. */
  afterContent?: ReactNode
}

export function SoftwareEntityDetail({
  title,
  era,
  year,
  publisher,
  coverArtUrl,
  launchCount,
  lastLaunchedAt,
  installedStatus,
  mediaSizeBytes,
  topControl,
  metaBefore,
  metaAfter,
  tags,
  editForm,
  editFormContent,
  advancedSection,
  fetchMetadataAction,
  beforeLaunch,
  onLaunch,
  launching,
  launchDisabled,
  launchButtonLabel,
  launchNote,
  launchSuccess,
  launchWarnings,
  launchError,
  launchErrorAction,
  restrictions,
  launchHistory,
  launchHistoryCanDelete,
  afterContent,
}: SoftwareEntityDetailProps) {
  const eraCode = era && era !== 'unknown' ? (ERA_LABEL[era] ?? era.toUpperCase()) : null
  const eraColor = era ? (ERA_COLOR[eraCode ?? ''] ?? undefined) : undefined
  const hasChipLine = eraCode || year || publisher
  const placeholderStyle = era ? (ERA_PLACEHOLDER[era] ?? ERA_PLACEHOLDER_DEFAULT) : ERA_PLACEHOLDER_DEFAULT
  const hasAtAGlance = installedStatus != null || (mediaSizeBytes != null && mediaSizeBytes > 0)

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title={title} />

      <div className="p-6">
        <div className="mb-6">
          <Link to="/software" className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
            ← Software
          </Link>
        </div>

        <div className="max-w-5xl space-y-6">

          {/* ── Header, not inside a card: cover art thumbnail left, title/era middle, Launch right (omitted entirely when onLaunch isn't supplied, e.g. Media) ── */}
          <div className="flex items-start gap-4">
            <div
              className="h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-surface-2"
              style={coverArtUrl ? undefined : { background: placeholderStyle.bg }}
            >
              {coverArtUrl && (
                <img src={coverArtUrl} alt={title} className="h-full w-full object-cover" />
              )}
            </div>

            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-semibold tracking-tight text-fg-1">{title}</h1>
              {hasChipLine && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {eraCode && (
                    <span
                      className="inline-flex shrink-0 items-center rounded-[4px] border px-[7px] py-1 font-mono text-[0.65625rem] font-medium leading-none tracking-[0.08em]"
                      style={{
                        color: eraColor,
                        borderColor: `color-mix(in srgb, ${eraColor} 42%, transparent)`,
                        background: `color-mix(in srgb, ${eraColor} 10%, transparent)`,
                      }}
                    >
                      {eraCode}
                    </span>
                  )}
                  {year && <span className="text-xs text-fg-3">{year}</span>}
                  {publisher && <span className="text-xs text-fg-3">{publisher}</span>}
                </div>
              )}
            </div>

            {onLaunch && (
              <div className="shrink-0">
                <LaunchSection
                  onLaunch={onLaunch}
                  launching={launching}
                  launchDisabled={launchDisabled}
                  launchButtonLabel={launchButtonLabel}
                  launchNote={launchNote}
                  launchSuccess={launchSuccess}
                  launchWarnings={launchWarnings}
                  launchError={launchError}
                  launchErrorAction={launchErrorAction}
                />
              </div>
            )}
          </div>

          {/* ── Compact read-only meta (era moved to the header chip above) ── */}
          {(metaBefore || (launchCount != null && launchCount > 0) || metaAfter) && (
            <section className="space-y-1 text-sm text-neutral-600 dark:text-neutral-300">
              {metaBefore}
              {launchCount != null && launchCount > 0 && (
                <div>
                  <span className="font-medium">Launches:</span> {launchCount}
                  {lastLaunchedAt && (
                    <> · Last {parseNaiveUtc(lastLaunchedAt).toLocaleDateString()}</>
                  )}
                </div>
              )}
              {metaAfter}
            </section>
          )}

          {/* ── Two-column body ── */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">

            <div className="min-w-0 space-y-6">
              {editForm && <EditForm {...editForm} />}
              {editFormContent}

              {beforeLaunch}

              {advancedSection && (
                <Card>
                  <AdvancedSection {...advancedSection} />
                </Card>
              )}
            </div>

            <div className="min-w-0 space-y-6">
              {tags && <TagsSection {...tags} />}

              {hasAtAGlance && (
                <Card>
                  <Card.Header>At a Glance</Card.Header>
                  <div className="space-y-3.5">
                    {installedStatus != null && (
                      <div>
                        <div className="text-[0.9375rem] font-semibold leading-none text-fg-1">
                          {installedStatus ? 'Yes' : 'No'}
                        </div>
                        <div className="mt-1 font-mono text-[0.6875rem] text-fg-3">installed</div>
                      </div>
                    )}
                    {mediaSizeBytes != null && mediaSizeBytes > 0 && (
                      <div>
                        <div className="text-[0.9375rem] font-semibold leading-none text-fg-1">
                          {formatBytes(mediaSizeBytes)}
                        </div>
                        <div className="mt-1 font-mono text-[0.6875rem] text-fg-3">media size</div>
                      </div>
                    )}
                  </div>
                </Card>
              )}

              {restrictions && (
                <Card>
                  <Card.Header>Restrictions</Card.Header>
                  <RestrictionsSection
                    users={restrictions.users}
                    restrictedIds={restrictions.restrictedIds}
                    restrictionsDirty={restrictions.restrictionsDirty}
                    toggleRestriction={restrictions.toggleRestriction}
                    onSave={restrictions.onSave}
                    saving={restrictions.saving}
                    error={restrictions.error}
                  />
                </Card>
              )}

              {fetchMetadataAction && (
                <Card>
                  <Card.Header>Metadata</Card.Header>
                  {fetchMetadataAction}
                </Card>
              )}

              {topControl}
            </div>

          </div>

          {afterContent}

          <LaunchHistorySection history={launchHistory ?? []} canDelete={launchHistoryCanDelete} />

        </div>
      </div>
    </div>
  )
}
