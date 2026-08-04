import type { StagedDisc } from './types';

export function newEntryId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// Immediate containing folder of a file picked via a `webkitdirectory` input
// (falls back to the file's own stem if no relative path is available, e.g.
// a plain file input).
export function folderNameFor(file: File): string {
  const relPath = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath;
  if (!relPath) return file.name.replace(/\.[^/.]+$/, '');
  const parts = relPath.split('/');
  return parts.length >= 2 ? parts[parts.length - 2] : parts[0];
}

// Recursively-picked folder(s) commonly reuse companion filenames per disc
// (e.g. every disc folder has its own "track.bin"), which would collide once
// flattened into one destination directory on the server. Original filenames
// aren't needed downstream (only executable_path/disc_number matter once
// ingested), so discard them entirely and rename from the containing folder
// instead: "{folder}{ext}" when a folder contributes one file of that
// extension, "{folder}_{n}{ext}" when it contributes more than one. This is a
// candidate name only, the existing sanitize_filename()/slugify() call in
// chunked_uploads.init_session() slugifies it server-side, so no frontend
// slugify is introduced here. Order is untouched: callers must still append
// the returned discs in the same order as the source FileList.
export function stageFolderFiles(fileList: FileList): StagedDisc[] {
  const files = Array.from(fileList);
  const groupKeys = files.map((file) => {
    const folder = folderNameFor(file);
    const dot = file.name.lastIndexOf('.');
    const ext = dot >= 0 ? file.name.slice(dot) : '';
    return { folder, ext, key: `${folder}::${ext}` };
  });
  const groupIndices = new Map<string, number[]>();
  groupKeys.forEach(({ key }, i) => {
    const indices = groupIndices.get(key) ?? [];
    indices.push(i);
    groupIndices.set(key, indices);
  });

  return files.map((file, i) => {
    const { folder, ext, key } = groupKeys[i];
    const indices = groupIndices.get(key)!;
    const candidateName =
      indices.length > 1 ? `${folder}_${indices.indexOf(i) + 1}${ext}` : `${folder}${ext}`;
    const renamed = new File([file], candidateName, { type: file.type });
    return { id: newEntryId(), file: renamed };
  });
}
