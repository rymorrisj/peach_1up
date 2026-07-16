import type { ReactNode } from 'react'
import type { components } from '@shared/types'
import type { RestrictionDomain } from '@/hooks/useCollectionRestrictions'
import type { LibraryModalConfig } from './components/LibraryModal'

export type TagRead = components['schemas']['TagRead']
type UserItemRead = components['schemas']['UserItemRead']

// Server-side pagination envelope (backend models/pagination.py), shared by
// every /api/v1/*-item(s)/*-bundle(s) list route across all three domains.
export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// Fields confirmed present on every domain's bundle-level read schema
// (Game/Media/App). created_at/updated_at are typed Optional here because
// Media's backend schema marks them Optional while Game/App's don't —
// treating them as optional everywhere keeps this shape safe for all three.
// Domain-specific fields (era, content_rating, is_pc, media_kind, ...) stay
// out of this shape and live on each domain's own extended type instead.
export interface EntityBundleBase {
  id: number
  slug: string | null
  title: string
  description: string | null
  tags: TagRead[]
  created_at?: string | null
  updated_at?: string | null
}

// Cover art location differs per domain (Game/App: leaf item keyed by
// display/launch disk id; Media: directly on the bundle), so it's resolved
// by a domain-supplied function rather than assumed as a shared field.
export type CoverArtResolver<TBundle> = (bundle: TBundle) => string | null

// Shared by Game and App bundles, whose cover art lives on whichever leaf
// item display_disk_id (falling back to launch_disk_id) points at — Media
// has no leaf indirection, its cover art is a direct bundle field instead.
export function resolveLeafCoverArt<TLeaf extends { id: number; cover_art_url: string | null }>(
  items: TLeaf[],
  displayDiskId: number | null,
  launchDiskId: number | null,
): string | null {
  const effectiveId = displayDiskId ?? launchDiskId
  const item = items.find((i) => i.id === effectiveId) ?? items[0]
  return item?.cover_art_url ?? null
}

// Single source of truth for turning the backend-computed launch_blocked_reason
// into the launch button's disabled state, label, and note. Shared by
// gameConfig and appConfig so both domains present identical UX and neither
// keeps its own client-side block condition. The backend reason is authoritative:
// null means "not blocked". *isLaunching* only adds the transient in-flight
// disable on top of the reason.
export interface LaunchGate {
  launchDisabled: boolean
  launchButtonLabel: string
  launchNote: string | null
}

export function launchGateFromReason(
  reason: string | null | undefined,
  isLaunching: boolean,
): LaunchGate {
  switch (reason) {
    case 'no_profile':
      return {
        launchDisabled: true,
        launchButtonLabel: 'Assign a profile to launch',
        launchNote: 'Assign a launch profile to enable launch.',
      }
    case 'no_environment':
      return {
        launchDisabled: true,
        launchButtonLabel: 'Configure an Environment to launch',
        launchNote: 'Create an Environment for this era to enable launch.',
      }
    default:
      return {
        launchDisabled: isLaunching,
        launchButtonLabel: 'Launch',
        launchNote: null,
      }
  }
}

// Per-domain wiring an EntityListPage/EntityDetailPage consumes so the
// generic components carry no built-in knowledge of any one domain.
// Only 'game' and 'app' can launch — Media supplies no launch config at all,
// and EntityDetailPage never renders a Launch section without one.
export interface EntityDomainConfig<TBundle extends EntityBundleBase> {
  domain: RestrictionDomain
  routeBase: string // e.g. '/software/games'
  listApiPath: string // e.g. '/api/v1/game-items'
  // Fetches the bundle by whatever config.identifierParam selects (a numeric
  // id as a string for 'id', a slug for 'slug') — always a string since it's
  // only ever interpolated into a URL, never used arithmetically.
  bundleApiPath: (identifier: string) => string // e.g. id => `/api/v1/game-item-bundle/${id}`
  tagEntityType: string // e.g. 'game_item_bundle' — must match backend _ASSIGNMENT_TARGETS
  entityLabel: string // singular, e.g. 'game'
  entityLabelPlural: string // e.g. 'games'
  coverArt: CoverArtResolver<TBundle>
  launchTargetType?: 'collection' | 'app' // omitted entirely for Media
  // Per-entity launch gate on top of launchTargetType — e.g. App launch is
  // PC-scoped only (bundle.is_pc), not every app in the domain is launchable.
  // Defaults to "launchable" whenever launchTargetType is set.
  isLaunchable?: (bundle: TBundle) => boolean
  // Route param this domain's detail page is keyed by. Defaults to the
  // numeric ':id' (App/Media's existing routes). Game has no numeric-id
  // lookup endpoint and is routed/fetched by slug instead.
  identifierParam?: 'id' | 'slug'
  // Back-link label on the loading/not-found guard screens ("← {label}").
  // Defaults to 'Back', matching App/Media's current text exactly.
  backLabel?: string
  // Whether to show entity.description as a read-only paragraph in the meta
  // section. Defaults to true (App/Media's only surface for description
  // today). Game suppresses this — its own edit-form slot already edits and
  // displays description, so this would otherwise duplicate it.
  showDescriptionMeta?: boolean
  // Filters the user list passed into the Restrictions section. Defaults to
  // identity (App/Media's current, unfiltered behavior). Game excludes
  // owners, since owners are never restrictable.
  filterRestrictionUsers?: (users: UserItemRead[]) => UserItemRead[]
  // Domain-specific stateful "extras" — additional hooks plus the derived
  // JSX slots that don't fit the shared shape (disc reorder, edit form,
  // delete flow, xiso convert, metadata enrich, DOS-install, etc. for Game).
  // Called unconditionally on every render, exactly like a custom hook, so
  // it must tolerate `entity` being undefined internally (pre-load). Omitted
  // entirely for App/Media, so their rendered output is unaffected.
  renderExtras?: (ctx: EntityDetailExtrasContext<TBundle>) => EntityDetailExtras
  // Drives the "+ Add {entityLabel}" affordance EntityListPage renders in its
  // TopBar. Omitted entirely for domains with no creation UI. Game does not
  // use this. Games.tsx is a bespoke page that wires LibraryModal directly
  // (see gameConfig.tsx's gameUploadModalConfig/gameScanModalConfig) rather
  // than going through EntityListPage.
  uploadConfig?: LibraryModalConfig
}

export interface EntityDetailExtrasContext<TBundle extends EntityBundleBase> {
  entity: TBundle | undefined
  entityId: number | undefined
  detailQueryKey: unknown[]
  isOwner: boolean
  launch: (profileId?: number | null) => void
  isLaunching: boolean
  launchErrorType: string | undefined
  refetchEntity: () => Promise<TBundle>
}

// JSX-shaped slots use ReactNode directly. editForm/advancedSection/
// launchHistory stay `unknown` here since this file has no business knowing
// EditForm/AdvancedSection/LaunchHistorySection's real shapes — EntityDetailPage
// casts them once, at the single point it spreads into SoftwareEntityDetail,
// which already owns those real types.
export interface EntityDetailExtras {
  eraLabel?: string
  launchCount?: number
  lastLaunchedAt?: string | null
  topControl?: ReactNode
  metaAfter?: ReactNode
  editForm?: unknown
  // Pre-rendered edit-form JSX for domains whose form isn't Game's EditForm
  // component (Media, App). Rendered in the same slot position as editForm,
  // generalized as ReactNode since each domain's form component differs and
  // gameConfig.tsx/EditForm.tsx stay untouched (see SoftwareEntityDetail.tsx).
  editFormContent?: ReactNode
  advancedSection?: unknown
  fetchMetadataAction?: ReactNode
  beforeLaunch?: ReactNode
  launchDisabled?: boolean
  launchButtonLabel?: string
  launchNote?: ReactNode
  launchErrorAction?: ReactNode
  launchHistory?: unknown[]
  onLaunch?: () => void
  afterContent?: ReactNode
}
