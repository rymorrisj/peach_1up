import { Button } from '@/ui';

// Every file physically belonging to a Media item bundle (one MediaItem row
// per file, always populated at ingest, see backend/models/media.py). Openable
// types (currently image) link out to the file's servable URL; every other
// kind still lists its filename so nothing on disk is hidden from the user.
const OPENABLE_MEDIA_KINDS = new Set(['image']);

function basename(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  const parts = normalized.split('/');
  return parts[parts.length - 1] || path;
}

function formatBytes(bytes: number | null): string | null {
  if (bytes == null) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export interface FileListEntry {
  id: number;
  file_path: string;
  file_url: string | null;
  file_size_bytes: number | null;
  media_kind: string;
}

export interface LinkedGameRef {
  entity_id: number;
  title: string;
}

interface FilesSectionProps {
  items: FileListEntry[];
  // Bundle's current cover_art_path (raw path, not the servable URL), so an
  // image already set as cover art can show its state instead of a redundant
  // "set as cover art" action. Omitted entirely (both this and onSetCoverArt)
  // when the caller has no cover art concept to wire up.
  currentCoverArtPath?: string | null;
  onSetCoverArt?: (filePath: string) => void;
  settingCoverArt?: boolean;
  // Every game_item_bundle this media item is linked to (via MediaLink),
  // pre-filtered by the caller from collection.linked_items. Omitted or
  // empty hides the "also set as game cover art" action entirely, matching
  // onSetCoverArt/currentCoverArtPath's own omit-when-unwired convention.
  linkedGameItems?: LinkedGameRef[];
  onApplyCoverArtToGames?: (filePath: string) => void;
  applyingCoverArtToGames?: boolean;
}

export function FilesSection({
  items,
  currentCoverArtPath,
  onSetCoverArt,
  settingCoverArt,
  linkedGameItems,
  onApplyCoverArtToGames,
  applyingCoverArtToGames,
}: FilesSectionProps) {
  if (items.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Files
      </h2>
      <ul className="space-y-1">
        {items.map((item) => {
          const name = basename(item.file_path);
          const size = formatBytes(item.file_size_bytes);
          const openable = OPENABLE_MEDIA_KINDS.has(item.media_kind) && item.file_url != null;
          const isCoverArt = currentCoverArtPath != null && item.file_path === currentCoverArtPath;
          return (
            <li key={item.id} className="flex items-center gap-2 text-sm">
              {openable ? (
                <a
                  href={item.file_url as string}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 hover:underline dark:text-blue-400"
                >
                  {name}
                </a>
              ) : (
                <span className="text-neutral-600 dark:text-neutral-300">{name}</span>
              )}
              {size && (
                <span className="text-xs text-neutral-400 dark:text-neutral-500">{size}</span>
              )}
              {openable &&
                onSetCoverArt &&
                (isCoverArt ? (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">Cover art</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={settingCoverArt}
                    onClick={() => onSetCoverArt(item.file_path)}
                  >
                    Set as cover art
                  </Button>
                ))}
              {openable &&
                onApplyCoverArtToGames &&
                linkedGameItems &&
                linkedGameItems.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={applyingCoverArtToGames}
                    onClick={() => onApplyCoverArtToGames(item.file_path)}
                  >
                    {linkedGameItems.length === 1
                      ? `Also set as ${linkedGameItems[0].title} cover art`
                      : `Also set as cover art for ${linkedGameItems.length} linked games`}
                  </Button>
                )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
