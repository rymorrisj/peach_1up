import type { components } from '@shared/types'
import type { RestrictionDomain } from '@/hooks/useCollectionRestrictions'

export type TagRead = components['schemas']['TagRead']

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

// Per-domain wiring an EntityListPage/EntityDetailPage consumes so the
// generic components carry no built-in knowledge of any one domain.
// Only 'game' and 'app' can launch — Media supplies no launch config at all,
// and EntityDetailPage never renders a Launch section without one.
export interface EntityDomainConfig<TBundle extends EntityBundleBase> {
  domain: RestrictionDomain
  routeBase: string // e.g. '/software/games'
  listApiPath: string // e.g. '/api/v1/game-items'
  bundleApiPath: (id: number) => string // e.g. id => `/api/v1/game-item-bundle/${id}`
  tagEntityType: string // e.g. 'game_item_bundle' — must match backend _ASSIGNMENT_TARGETS
  entityLabel: string // singular, e.g. 'game'
  entityLabelPlural: string // e.g. 'games'
  coverArt: CoverArtResolver<TBundle>
  launchTargetType?: 'collection' | 'app' // omitted entirely for Media
  // Per-entity launch gate on top of launchTargetType — e.g. App launch is
  // PC-scoped only (bundle.is_pc), not every app in the domain is launchable.
  // Defaults to "launchable" whenever launchTargetType is set.
  isLaunchable?: (bundle: TBundle) => boolean
}
