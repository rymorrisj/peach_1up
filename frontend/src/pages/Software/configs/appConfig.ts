import type { EntityBundleBase, EntityDomainConfig } from '../types'
import { resolveLeafCoverArt } from '../types'

export interface AppItemLeaf {
  id: number
  app_item_bundle_id: number
  file_path: string
  executable_path: string | null
  cover_art_path: string | null
  cover_art_url: string | null
}

export interface AppItemBundleData extends EntityBundleBase {
  is_pc: boolean
  category: string | null
  publisher: string | null
  developer: string | null
  year: number | null
  installed: boolean
  environment_item_id: number | null
  profile_item_id: number | null
  launch_disk_id: number | null
  display_disk_id: number | null
  last_launched_at: string | null
  launch_count: number
  items: AppItemLeaf[]
}

// App's cover art lives on the leaf item (same indirection as Game — see
// resolveLeafCoverArt). Launch is domain-enabled ('app' targetType) but
// per-entity gated to PC apps only via isLaunchable (bundle.is_pc).
export const appDomainConfig: EntityDomainConfig<AppItemBundleData> = {
  domain: 'app',
  routeBase: '/software/apps',
  listApiPath: '/api/v1/app-items',
  bundleApiPath: (id) => `/api/v1/app-item-bundle/${id}`,
  tagEntityType: 'app_item_bundle',
  entityLabel: 'app',
  entityLabelPlural: 'apps',
  coverArt: (bundle) => resolveLeafCoverArt(bundle.items, bundle.display_disk_id, bundle.launch_disk_id),
  launchTargetType: 'app',
  isLaunchable: (bundle) => bundle.is_pc,
}
