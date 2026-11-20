// No shared frontend list of media extensions exists (the backend owns the
// authoritative one), so this is the simplest reasonable set of disc and
// cartridge image formats. It only decides which file may name an upload; the
// server still classifies everything on ingest.
const MEDIA_EXTENSIONS = new Set([
  'iso',
  'chd',
  'cue',
  'gdi',
  'bin',
  'img',
  'cso',
  'rvz',
  'wbfs',
  'gcm',
  'nrg',
  'mdf',
  'vhd',
  'pbp',
  'nds',
  '3ds',
  'nsp',
  'xci',
]);

function stemOf(name: string): string {
  return name.replace(/\.[^/.]+$/, '');
}

function isMediaFile(name: string): boolean {
  const dot = name.lastIndexOf('.');
  return dot > 0 && MEDIA_EXTENSIONS.has(name.slice(dot + 1).toLowerCase());
}

function selectedFolderName(file: File): string {
  const relPath = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath;
  return relPath ? relPath.split('/')[0] : '';
}

/**
 * Default Title for a folder selection. Exactly one media file: its name
 * without the extension, unchanged ("Armored Core (USA).chd" -> "Armored Core
 * (USA)"). Anything else (several media files, none): the selected folder's
 * name, which is the first segment of webkitRelativePath. Sidecars such as
 * cover.jpg never count. Returns '' for an empty selection.
 */
export function defaultUploadTitle(files: File[]): string {
  if (files.length === 0) return '';
  const media = files.filter((f) => isMediaFile(f.name));
  if (media.length === 1) return stemOf(media[0].name);
  return selectedFolderName(files[0]);
}
