import type { GameItemBundleData } from './CollectionCard';
import { resolveLeafCoverArt } from '../types';

// Game's cover art lives on the leaf item (keyed by display/launch disk id),
// not the bundle itself, this is the CoverArtResolver<GameItemBundleData>.
export function getGameCoverArt(bundle: GameItemBundleData): string | null {
  return resolveLeafCoverArt(bundle.items, bundle.display_disk_id, bundle.launch_disk_id);
}
