import type { EntityBundleBase, EntityDomainConfig } from '../types'

export interface MediaItemLeaf {
  id: number
  media_item_bundle_id: number | null
  file_path: string
  cover_art_path: string | null
  cover_art_url: string | null
}

export interface MediaItemBundleData extends EntityBundleBase {
  media_kind: string
  cover_art_path: string | null
  cover_art_url: string | null
  items: MediaItemLeaf[]
}

// Media has no launch capability at all (no launchTargetType), and its cover
// art lives directly on the bundle rather than a leaf item (see discovery:
// cover_art_url is bundle-level for Media, leaf-level for Game/App).
export const mediaDomainConfig: EntityDomainConfig<MediaItemBundleData> = {
  domain: 'media',
  routeBase: '/software/media',
  listApiPath: '/api/v1/media-item-bundles',
  bundleApiPath: (id) => `/api/v1/media-item-bundle/${id}`,
  tagEntityType: 'media_item_bundle',
  entityLabel: 'media item',
  entityLabelPlural: 'media',
  coverArt: (bundle) => bundle.cover_art_url ?? null,
}
