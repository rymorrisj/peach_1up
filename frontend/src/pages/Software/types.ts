import type { ReactNode } from 'react'
import type { components } from '@shared/types'
import type { RestrictionDomain } from '@/hooks/useCollectionRestrictions'
import type { LibraryModalConfig } from './components/LibraryModal'

export type TagRead = components['schemas']['TagRead']
export type LinkedEntityRef = components['schemas']['LinkedEntityRef']
type UserItemRead = components['schemas']['UserItemRead']

// Single source of truth for each domain's detail-route base, referenced by
// both the domain's own EntityDomainConfig.routeBase and the entity-link
// resolver (LinkedItemsSection.tsx), so the two never drift apart.
export const GAME_ROUTE_BASE = '/software/games'
export const MEDIA_ROUTE_BASE = '/software/media'
export const APP_ROUTE_BASE = '/software/apps'

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
  linked_items: LinkedEntityRef[]
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

// Filter bar support for EntityListPage, presence-gated the same pattern as
// uploadConfig: a domain that omits `filters` entirely gets no filter bar and
// no change to its list query params. Modeled on Games.tsx's Filters state
// (era + profileFilter). Game (GET /api/v1/game-items, game_item_bundles.py:
// list_game_items) and App (GET /api/v1/app-items, apps.py:list_apps) both
// have backend support for era and profile_assigned. Media has no era/profile
// concept at all, so it leaves this unset.
export interface EntityFilterConfig {
  // Renders an "All eras" + ERA_LABELS select, synced to the `?era=` URL
  // search param (survives navigation/back-button, mirrors Games.tsx) and
  // serialized as `?era=` on the list request.
  era?: boolean
  // Renders an "All / Profile assigned / No profile" select, serialized as
  // `?profile_assigned=true|false` on the list request. Not URL-synced,
  // matching Games.tsx (era is the only URL-synced filter there).
  profileAssigned?: boolean
  // Renders an "All tags" + tag-name select, serialized as `?tag=` on the
  // list request. Not URL-synced, same as profileAssigned. The backend
  // `tag` param (list_game_items/list_apps/list_media_item_bundles) matches
  // a single tag by exact `Tag.name`, not id, and not a multi-value list, so
  // this is a single-select control, not a multi-select typeahead. Shared by
  // all three domains since tags (unlike era/profile) are the one filter
  // dimension genuinely common across Game, App, and Media.
  tag?: boolean
}

// Universal sort options for EntityListPage's list pages. title (alphabetical)
// and date_added (recently added first) are the only two fields confirmed
// present on every domain's bundle model (title, created_at on Game/App/Media
// — see backend/service/utils/sort_utils.py, which enforces this exact same
// value set server-side). Declared once and reused by all three domain
// configs rather than each declaring its own list, since there is no
// domain-specific sort field today; adding one would need its own proposal.
export const SOFTWARE_SORT_OPTIONS: { value: string; label: string }[] = [
  { value: 'title', label: 'Title (A-Z)' },
  { value: 'date_added', label: 'Recently added' },
]

// Leaf shape the multi-disc disc-selector strip needs, a subset of
// Game/App's leaf item fields, kept minimal so any domain with a
// disc/part-numbered leaf collection can supply it.
export interface EntityMultiDiscLeaf {
  id: number
  disc_number: number
  cover_art_url: string | null
}

// Config-gated multi-disc display-disk selection, ported from Games.tsx's
// onSetDisplayDisk (CollectionCard.tsx). Presence on EntityDomainConfig gates
// EntityCard's disc-selector strip entirely, a domain that omits `multiDisc`
// renders the plain single-thumbnail card with no strip, no behavior change.
// No domain opts into this yet (Media/App have no multi-disc concept); this
// is slot-readiness for a future domain, ported only so the capability exists.
export interface EntityMultiDiscConfig<TBundle> {
  // Extracts this bundle's leaf items for the strip. Bundles with 0 or 1 item
  // never render the strip regardless of this config being present.
  items: (bundle: TBundle) => EntityMultiDiscLeaf[]
  displayDiskId: (bundle: TBundle) => number | null
  launchDiskId: (bundle: TBundle) => number | null
  // Persists the new display disk (mirrors Games.tsx's handleSetDisplayDisk).
  // Should only perform the write. EntityListPage invalidates the list query
  // itself afterward, the same way it already does for uploadConfig's
  // onComplete, so this callback doesn't need to know the query key.
  onSetDisplayDisk: (entityId: number, discId: number) => Promise<void>
}

// Config-gated delete-media-override + two-step confirm-token delete flow,
// ported from Games.tsx's handleRemove / useDeleteCollection. This is *not*
// simply "on for every domain": Game and App's backends both expose the full
// contract (POST .../confirm-delete issues a token, DELETE
// .../{id}?confirmation_token=... consumes it, plus a delete_media_override
// field on the bundle's PATCH schema, see game_item_bundles.py/apps.py and
// GameItemBundleUpdate/AppItemBundleUpdate). Media's backend has neither:
// delete_media_item_bundle is a plain DELETE with no confirmation_token
// parameter at all, and MediaItemBundleUpdate has no delete_media_override
// field. A domain without deleteConfig keeps EntityListPage's original plain
// confirm+DELETE behavior (Media's correct, unchanged path); a domain that
// supplies it gets Game's full two-step UX (App opts in, see appConfig.tsx).
export interface EntityDeleteConfig<TBundle> {
  // Base path for this entity keyed by its numeric id, e.g.
  // id => `/api/v1/app-item-bundle/${id}`. Deliberately independent of
  // config.bundleApiPath, whose identifier may not be the numeric id (Game's
  // is slug-keyed for GET/PATCH); confirm-delete/DELETE are always id-keyed.
  bundleByIdApiPath: (id: number) => string
  // Reads this entity's persisted delete_media_override (null/undefined =
  // inherit the global delete_media_on_removal default from
  // /api/v1/settings/library-defaults). Domains without such a field on their
  // model should omit deleteConfig entirely rather than supply a resolver
  // that always returns null.
  resolveDeleteMediaOverride: (entity: TBundle) => boolean | null
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
  launchTargetType?: 'game_item_bundle' | 'app' // omitted entirely for Media
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
  useRenderExtras?: (ctx: EntityDetailExtrasContext<TBundle>) => EntityDetailExtras
  // Drives the "+ Add {entityLabel}" affordance EntityListPage renders in its
  // TopBar. Omitted entirely for domains with no creation UI. Game does not
  // use this. Games.tsx is a bespoke page that wires LibraryModal directly
  // (see gameConfig.tsx's gameUploadModalConfig/gameScanModalConfig) rather
  // than going through EntityListPage.
  uploadConfig?: LibraryModalConfig
  // Second modal slot, structurally alongside uploadConfig, renders a
  // "Scan Directory" button and a second <LibraryModal> instance (mode:
  // 'scan') when present. Slot-readiness only: no domain supplies this yet,
  // Scan itself is not wired for Media or App this pass, and Games.tsx (the
  // only domain with a working Scan today) stays on its own bespoke
  // two-button/two-modal layout, untouched.
  scanConfig?: LibraryModalConfig
  // Era/profile filter bar, see EntityFilterConfig. Omitted for Media.
  filters?: EntityFilterConfig
  // Sort control for EntityListPage's list query, presence-gated the same way
  // uploadConfig/filters are: a domain that omits this renders no sort
  // control and sends no `?sort=` param, identical to pre-sort behavior. All
  // three Software domains supply SOFTWARE_SORT_OPTIONS verbatim today.
  sortOptions?: { value: string; label: string }[]
  // Multi-disc display-disk selector, see EntityMultiDiscConfig. Omitted for
  // every domain today (slot-readiness only).
  multiDisc?: EntityMultiDiscConfig<TBundle>
  // Delete-media-override + two-step confirm-token delete flow, see
  // EntityDeleteConfig. Omitted means EntityListPage's original plain
  // confirm+DELETE behavior (Media's correct path, backend has no token
  // contract or override field).
  deleteConfig?: EntityDeleteConfig<TBundle>
  // Full custom card renderer for a domain whose grid card departs from
  // EntityCard's generic layout. Game's CollectionCard has stacked-disc
  // background layers, an era-tinted placeholder with publisher/year, a
  // stack-count badge, and a display-vs-launch-disc divergence badge, none
  // of which EntityCard renders (EntityCard is deliberately the simple,
  // era-agnostic card Media/App use). When set, EntityListPage renders this
  // instead of <EntityCard> for every entity in the grid. Omitted for Media
  // and App, whose rendering via EntityCard is unchanged.
  renderCard?: (props: {
    entity: TBundle
    onRemove: (entity: TBundle) => void
    onSetDisplayDisk?: (entityId: number, discId: number) => void
  }) => ReactNode
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
  // Raw era slug (e.g. "ps1"), not a pre-formatted label, so the header chip
  // can look up both its short display code and its token color from
  // types/era.ts the same way grid cards already do. Omitted entirely for
  // domains with no era concept (Media).
  era?: string
  year?: number | null
  publisher?: string | null
  launchCount?: number
  lastLaunchedAt?: string | null
  // At a Glance stats. See SoftwareEntityDetail.tsx for the omit-vs-fabricate
  // rule: undefined/null renders no tile rather than a fake zero/false.
  installedStatus?: boolean
  mediaSizeBytes?: number | null
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
