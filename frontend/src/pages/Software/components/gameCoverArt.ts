import type { GameItemBundleData } from './CollectionCard';

// Game's cover art lives on the leaf item (keyed by display/launch disk id),
// not the bundle itself, this is the CoverArtResolver<GameItemBundleData>.
export function getGameCoverArt(bundle: GameItemBundleData): string | null {
  const effectiveDisplayId = bundle.display_disk_id ?? bundle.launch_disk_id;
  const displayDisc = bundle.items.find((d) => d.id === effectiveDisplayId) ?? bundle.items[0];
  return displayDisc?.cover_art_url ?? null;
}
