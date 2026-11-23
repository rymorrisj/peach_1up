import { File as FileIcon, FileAudio, FileText, FileVideo, Image as ImageIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '@/ui';
import { pathKey } from '@/lib/pathKey';
import { CoverImage } from './CoverImage';

// Every file physically belonging to a Media item bundle (one MediaItem row
// per file, always populated at ingest, see backend/models/media.py). Image
// files render as thumbnails that open the servable URL; every other kind
// still gets a titled tile so nothing on disk is hidden from the user.
const OPENABLE_MEDIA_KINDS = new Set(['image']);

// Fetch Metadata asset types (backend/service/metadata_providers/__init__.py),
// in display order. Groups for these come first.
const ASSET_TYPE_LABELS: Record<string, string> = {
  cover: 'Cover',
  boxart_front: 'Box art (front)',
  boxart_back: 'Box art (back)',
  screenshot: 'Screenshots',
  fanart: 'Fan art',
  banner: 'Banners',
  clearlogo: 'Clear logos',
  icon: 'Icons',
};

// Files with no asset_type (manual uploads) group under their media kind.
const MEDIA_KIND_LABELS: Record<string, string> = {
  image: 'Images',
  audio: 'Audio',
  video: 'Video',
  text: 'Text',
};

const KIND_ICONS: Record<string, ReactNode> = {
  image: <ImageIcon className="h-8 w-8" aria-hidden="true" />,
  audio: <FileAudio className="h-8 w-8" aria-hidden="true" />,
  video: <FileVideo className="h-8 w-8" aria-hidden="true" />,
  text: <FileText className="h-8 w-8" aria-hidden="true" />,
};

const GROUP_ORDER = [
  ...Object.keys(ASSET_TYPE_LABELS).map((type) => `asset:${type}`),
  ...Object.keys(MEDIA_KIND_LABELS).map((kind) => `kind:${kind}`),
];
const UNLISTED_RANK = GROUP_ORDER.length;
const OTHER_KEY = 'other';

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
  title: string;
  file_path: string;
  file_url: string | null;
  file_size_bytes: number | null;
  media_kind: string;
  asset_type: string | null;
}

export interface LinkedGameRef {
  entity_id: number;
  title: string;
}

interface FileGroup {
  key: string;
  label: string;
  entries: FileListEntry[];
}

function groupOf(entry: FileListEntry): { key: string; label: string } {
  if (entry.asset_type) {
    return {
      key: `asset:${entry.asset_type}`,
      label: ASSET_TYPE_LABELS[entry.asset_type] ?? entry.asset_type.replace(/_/g, ' '),
    };
  }
  if (entry.media_kind in MEDIA_KIND_LABELS) {
    return { key: `kind:${entry.media_kind}`, label: MEDIA_KIND_LABELS[entry.media_kind] };
  }
  return { key: OTHER_KEY, label: 'Other' };
}

function groupFiles(items: FileListEntry[]): FileGroup[] {
  const groups = new Map<string, FileGroup>();
  for (const entry of items) {
    const { key, label } = groupOf(entry);
    const group = groups.get(key) ?? { key, label, entries: [] };
    group.entries.push(entry);
    groups.set(key, group);
  }
  const rank = (key: string) => {
    if (key === OTHER_KEY) return UNLISTED_RANK + 1;
    const index = GROUP_ORDER.indexOf(key);
    return index === -1 ? UNLISTED_RANK : index;
  };
  return [...groups.values()].sort((a, b) => rank(a.key) - rank(b.key));
}

interface FilesSectionProps {
  items: FileListEntry[];
  // Bundle's current cover_art_path (raw path, not the servable URL), so an
  // image already set as cover art can show its state instead of a redundant
  // "set as cover art" action. Compared as normalised paths. Omitted entirely
  // (both this and onSetCoverArt) when the caller has no cover art concept
  // to wire up.
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

  const coverKey = currentCoverArtPath ? pathKey(currentCoverArtPath) : null;

  return (
    <section className="space-y-4">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Files
      </h2>
      {groupFiles(items).map((group) => (
        <div key={group.key} className="space-y-2">
          <h3 className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
            {group.label} ({group.entries.length})
          </h3>
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-3">
            {group.entries.map((item) => {
              const name = basename(item.file_path);
              const title = item.title || name;
              const size = formatBytes(item.file_size_bytes);
              const openable = OPENABLE_MEDIA_KINDS.has(item.media_kind) && item.file_url != null;
              const isCoverArt = coverKey != null && pathKey(item.file_path) === coverKey;
              const placeholder = (
                <div className="flex h-full w-full items-center justify-center text-neutral-400 dark:text-neutral-500">
                  {KIND_ICONS[item.media_kind] ?? (
                    <FileIcon className="h-8 w-8" aria-hidden="true" />
                  )}
                </div>
              );
              return (
                <li key={item.id} className="flex min-w-0 flex-col gap-1.5 text-sm">
                  <div className="aspect-square overflow-hidden rounded-md border border-neutral-200 bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-800">
                    {openable ? (
                      <a
                        href={item.file_url as string}
                        target="_blank"
                        rel="noreferrer"
                        className="block h-full w-full"
                      >
                        <CoverImage
                          src={item.file_url}
                          alt={title}
                          className="h-full w-full object-cover"
                          fallback={placeholder}
                        />
                      </a>
                    ) : (
                      placeholder
                    )}
                  </div>
                  <span title={name} className="truncate text-neutral-700 dark:text-neutral-200">
                    {title}
                  </span>
                  {size && (
                    <span className="text-xs text-neutral-400 dark:text-neutral-500">{size}</span>
                  )}
                  {openable &&
                    onSetCoverArt &&
                    (isCoverArt ? (
                      <span className="text-xs text-neutral-400 dark:text-neutral-500">
                        Cover art
                      </span>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="whitespace-normal"
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
                        className="whitespace-normal"
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
        </div>
      ))}
    </section>
  );
}
