import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { chunkedUpload } from '@/lib/chunkedUpload';
import { apiFetch, ApiError } from '@/api/client';
import { useAppContext } from '@/context/useAppContext';
import { useConfirm } from '@/hooks/useConfirm';
import ConfirmModal from '@/components/common/ConfirmModal';
import { Button, Modal, Checkbox } from '@/ui';
import { newEntryId, stageFolderFiles } from './helpers';
import SingleFileMode from './SingleFileMode';
import MultiDiscMode from './MultiDiscMode';
import FolderUploadMode from './FolderUploadMode';
import BrowseImportPanel from './BrowseImportPanel';
import type {
  LibraryModalProps,
  UploadEntry,
  StagedDisc,
  BrowseImportEntry,
  ImportFromPathResult,
} from './types';

export default function UploadBody({
  open,
  onClose,
  onComplete,
  mediaPath,
  config,
}: LibraryModalProps) {
  const { state, dispatch } = useAppContext();
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const [dragActive, setDragActive] = useState(false);

  const supportsMultiDisc = config.supportsMultiDisc ?? false;
  const supportsFolderMode = config.supportsFolderMode ?? false;
  const supportsBrowseImport = Boolean(config.importFromPathApiPath);

  // Multi-disc state
  const [multiDisc, setMultiDisc] = useState(false);
  const [stagedDiscs, setStagedDiscs] = useState<StagedDisc[]>([]);
  const [discSetTitle, setDiscSetTitle] = useState('');
  const [folderName, setFolderName] = useState('');
  const [folderNameTouched, setFolderNameTouched] = useState(false);
  const [setStatus, setSetStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  const [setError, setSetError] = useState<string | null>(null);
  const [setProgress, setSetProgress] = useState(0);
  const [setBackground, setSetBackground] = useState(false);
  const [setJobId, setSetJobId] = useState<string | null>(null);

  // Folder upload state
  const [folderMode, setFolderMode] = useState(false);
  const [folderFiles, setFolderFiles] = useState<File[]>([]);
  const [folderTitle, setFolderTitle] = useState('');
  const [folderStatus, setFolderStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>(
    'idle',
  );
  const [folderError, setFolderError] = useState<string | null>(null);
  const [folderProgress, setFolderProgress] = useState(0);
  const [folderBackground, setFolderBackground] = useState(false);
  const [folderJobId, setFolderJobId] = useState<string | null>(null);
  const [folderResult, setFolderResult] = useState<{
    type: 'item' | 'set';
    title: string;
    discCount?: number;
  } | null>(null);
  const folderAbortRef = useRef<(() => void) | null>(null);
  const setAbortRef = useRef<(() => void) | null>(null);
  const entryAbortsRef = useRef<Map<string, () => void>>(new Map());

  // Server-side-path import state, a second, independent source mechanism
  // alongside drag-and-drop/file-input above. Sourced via BrowsePanel (real,
  // absolute, server-resolved paths), not a browser File object, so unlike
  // every other entry list in this modal it can offer "delete original".
  const [browserOpen, setBrowserOpen] = useState(false);
  const [browseImports, setBrowseImports] = useState<BrowseImportEntry[]>([]);
  const [browseImporting, setBrowseImporting] = useState(false);
  const {
    confirm: confirmDeleteOriginal,
    isOpen: deleteConfirmOpen,
    options: deleteConfirmOptions,
    handleConfirm: handleDeleteConfirmed,
    handleCancel: handleDeleteCancelled,
  } = useConfirm();

  const { data: libraryDefaults, isLoading: libraryDefaultsLoading } = useQuery<{
    delete_media_on_removal: boolean;
    delete_original_on_upload: boolean;
  }>({
    queryKey: ['settings', 'library-defaults'],
    queryFn: () => apiFetch('/api/v1/settings/library-defaults'),
    staleTime: 60_000,
    enabled: open,
  });
  const deleteOriginalDefault = Boolean(libraryDefaults?.delete_original_on_upload);

  const busy =
    entries.some((e) => e.status === 'uploading') ||
    setStatus === 'uploading' ||
    folderStatus === 'uploading' ||
    browseImporting;

  // Narrower than `busy` above: this is what actually gates the Modal's own
  // dismiss paths (Escape, overlay click, Dialog.Close). Once an operation
  // has a job_id, it continues server-side and is tracked in the nav bell
  // regardless of whether this modal stays open, so dismissing it is safe,
  // only the pre-job_id window (the /init round-trip, or a browse-import
  // entry's request before it resolves to either a job_id or an inline
  // result) still needs to block dismissal. `busy` itself keeps its broad
  // meaning ("this operation's client-side work isn't done yet") because
  // it's also used to disable in-flight controls throughout this file and
  // MultiDiscMode/FolderUploadMode/BrowseImportPanel for their own full
  // duration, and by the reset effect below to know when it's actually safe
  // to discard local state, neither of those should narrow.
  const dismissBlocked =
    entries.some((e) => e.status === 'uploading' && !e.jobId) ||
    (setStatus === 'uploading' && !setJobId) ||
    (folderStatus === 'uploading' && !folderJobId) ||
    browseImports.some((e) => e.status === 'importing');

  // Resets all local state once the modal is closed and nothing is still
  // busy. Adjusted during render (tracking previous open/busy) rather than
  // in a useEffect: every reset here is a plain local setState call, and
  // most targets are already at their reset value, so re-running the block
  // on an unrelated render is harmless, only the [open, busy] transition
  // itself needs a guard to avoid doing this on every render.
  const [prevResetKey, setPrevResetKey] = useState({ open, busy });
  if (open !== prevResetKey.open || busy !== prevResetKey.busy) {
    setPrevResetKey({ open, busy });
    if (!open && !busy) {
      setEntries([]);
      setStagedDiscs([]);
      setDiscSetTitle('');
      setFolderName('');
      setFolderNameTouched(false);
      setSetStatus('idle');
      setSetError(null);
      setSetProgress(0);
      setSetBackground(false);
      setSetJobId(null);
      setMultiDisc(false);
      setFolderFiles([]);
      setFolderTitle('');
      setFolderStatus('idle');
      setFolderError(null);
      setFolderProgress(0);
      setFolderBackground(false);
      setFolderJobId(null);
      setFolderResult(null);
      setFolderMode(false);
      setBrowseImports([]);
      setBrowserOpen(false);
    }
  }

  // Default the folder-name field from the first staged disc's filename (or
  // the set title, if no disc is staged yet) until the user edits it
  // directly. Derived directly during render rather than in a useEffect:
  // setFolderName is called with a plain string, so once it stabilizes at
  // the derived value further identical calls are no-ops (no loop risk).
  if (!folderNameTouched) {
    if (stagedDiscs.length > 0) {
      setFolderName(
        stagedDiscs[0].file.name
          .replace(/\.[^/.]+$/, '')
          .replace(/[-_]/g, ' ')
          .trim(),
      );
    } else if (discSetTitle.trim()) {
      setFolderName(discSetTitle.trim());
    }
  }

  function startUpload(entry: UploadEntry) {
    const title = entry.file.name
      .replace(/\.[^/.]+$/, '')
      .replace(/[-_]/g, ' ')
      .trim();
    const { promise, abort } = chunkedUpload(
      'file',
      title,
      [entry.file],
      (pct) => {
        setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, progress: pct } : e)));
      },
      config.uploadDomain,
      (jobId) => {
        // Fires right after /init, before any chunk has been transferred, so
        // the nav bell tracks this upload from the start of the transfer,
        // not just its server-side finalize tail.
        dispatch({
          type: 'UPSERT_JOB',
          payload: {
            id: jobId,
            kind: 'upload',
            status: 'processing',
            progress: 0,
            message: `Uploading "${title}"…`,
          },
        });
        setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, jobId } : e)));
      },
    );
    entryAbortsRef.current.set(entry.id, abort);
    promise
      .then((res) => {
        // Every upload finalizes as a background job now, surfaced in the
        // nav bell (dispatched above, at init time). The item appears in the
        // grid once that job finishes (via the shared 'upload-complete'
        // window event, not onComplete() here).
        const jobId = res.body.job_id;
        setEntries((prev) =>
          prev.map((e) =>
            e.id === entry.id ? { ...e, status: 'success', progress: 100, jobId } : e,
          ),
        );
      })
      .catch((err: Error) => {
        setEntries((prev) =>
          prev.map((e) => (e.id === entry.id ? { ...e, status: 'error', error: err.message } : e)),
        );
      })
      .finally(() => {
        entryAbortsRef.current.delete(entry.id);
      });
  }

  function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (files.length === 0) return;

    if (multiDisc) {
      setStagedDiscs((prev) => [...prev, ...files.map((f) => ({ id: newEntryId(), file: f }))]);
      return;
    }

    const next: UploadEntry[] = files.map((file) => ({
      id: newEntryId(),
      file,
      progress: 0,
      status: 'uploading',
    }));
    setEntries((prev) => [...prev, ...next]);
    next.forEach(startUpload);
  }

  // Multi-disc + folder-upload combo: the picked folder's files are already
  // recursively enumerated by the browser (webkitdirectory walks the whole
  // tree), so this just renames for collision-safety and appends, no new
  // recursion logic, and append order is preserved (= upload order).
  function handleDiscFolderPick(fileList: FileList) {
    if (fileList.length === 0) return;
    setStagedDiscs((prev) => [...prev, ...stageFolderFiles(fileList)]);
  }

  function moveDisc(id: string, dir: -1 | 1) {
    setStagedDiscs((prev) => {
      const idx = prev.findIndex((d) => d.id === id);
      if (idx < 0) return prev;
      const next = [...prev];
      const swap = idx + dir;
      if (swap < 0 || swap >= next.length) return prev;
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next;
    });
  }

  function removeDisc(id: string) {
    setStagedDiscs((prev) => prev.filter((d) => d.id !== id));
  }

  async function submitSet() {
    const title = folderName.trim() || discSetTitle.trim();
    if (!title) return;
    if (stagedDiscs.length === 0) return;

    setSetStatus('uploading');
    setSetError(null);
    setSetProgress(0);
    setSetBackground(false);
    setSetJobId(null);

    const { promise, abort } = chunkedUpload(
      'set',
      title,
      stagedDiscs.map((d) => d.file),
      setSetProgress,
      config.uploadDomain,
      (jobId) => {
        // Fires right after /init, before any chunk has been transferred, so
        // the nav bell tracks this upload from the start of the transfer,
        // not just its server-side finalize tail, and dismissBlocked above
        // (fed by this same jobId) can drop as soon as there's a job to
        // track, letting Escape/overlay dismiss the modal early.
        dispatch({
          type: 'UPSERT_JOB',
          payload: {
            id: jobId,
            kind: 'upload',
            status: 'processing',
            progress: 0,
            message: `Uploading "${title}"…`,
          },
        });
        setSetJobId(jobId);
      },
    );
    setAbortRef.current = abort;
    try {
      const res = await promise;
      setSetBackground(true);
      setSetJobId(res.body.job_id);
      setSetStatus('success');
    } catch (err) {
      setSetStatus('error');
      setSetError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setAbortRef.current = null;
    }
  }

  async function submitFolderUpload() {
    if (!folderTitle.trim() || folderFiles.length === 0) return;

    const title = folderTitle.trim();
    setFolderStatus('uploading');
    setFolderError(null);
    setFolderProgress(0);
    setFolderBackground(false);
    setFolderJobId(null);

    const { promise, abort } = chunkedUpload(
      'folder',
      title,
      folderFiles,
      setFolderProgress,
      config.uploadDomain,
      (jobId) => {
        // Fires right after /init, before any chunk has been transferred, so
        // the nav bell tracks this upload from the start of the transfer,
        // not just its server-side finalize tail, and dismissBlocked above
        // (fed by this same jobId) can drop as soon as there's a job to
        // track, letting Escape/overlay dismiss the modal early.
        dispatch({
          type: 'UPSERT_JOB',
          payload: {
            id: jobId,
            kind: 'upload',
            status: 'processing',
            progress: 0,
            message: `Uploading "${title}"…`,
          },
        });
        setFolderJobId(jobId);
      },
    );
    folderAbortRef.current = abort;
    try {
      const res = await promise;
      setFolderBackground(true);
      setFolderJobId(res.body.job_id);
      setFolderResult({ type: 'item', title });
      setFolderStatus('success');
    } catch (err) {
      setFolderStatus('error');
      setFolderError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      folderAbortRef.current = null;
    }
  }

  // Each Browse click appends one entry, BrowsePanel is single-select, so
  // staging multiple sources means clicking "Browse Server Files…" once per
  // item, mirroring how "Select Disc Folder…" above is clicked once per disc.
  function handleBrowseSelect(path: string, isDir: boolean) {
    const name = path.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? path;
    setBrowseImports((prev) => [
      ...prev,
      {
        id: newEntryId(),
        path,
        name,
        isDir,
        deleteOriginal: deleteOriginalDefault,
        status: 'staged',
      },
    ]);
  }

  function toggleEntryDelete(id: string) {
    setBrowseImports((prev) =>
      prev.map((e) => (e.id === id ? { ...e, deleteOriginal: !e.deleteOriginal } : e)),
    );
  }

  function removeBrowseEntry(id: string) {
    setBrowseImports((prev) => prev.filter((e) => e.id !== id));
  }

  // Mirrors the scan body's toggleAll/allSelected pattern, applied to
  // deleteOriginal instead of an import-selection set, every staged entry is
  // always imported here, so there's no separate "select which to import"
  // step the way the scan preview has.
  function toggleDeleteAllOriginal() {
    setBrowseImports((prev) => {
      const staged = prev.filter((e) => e.status === 'staged');
      const allChecked = staged.length > 0 && staged.every((e) => e.deleteOriginal);
      const next = !allChecked;
      return prev.map((e) => (e.status === 'staged' ? { ...e, deleteOriginal: next } : e));
    });
  }

  async function submitBrowseImports() {
    const pending = browseImports.filter((e) => e.status === 'staged');
    if (pending.length === 0 || !config.importFromPathApiPath) return;
    const importPath = config.importFromPathApiPath;

    const toDelete = pending.filter((e) => e.deleteOriginal);
    if (toDelete.length > 0) {
      const confirmed = await confirmDeleteOriginal({
        title: `Delete ${toDelete.length} original ${toDelete.length === 1 ? 'item' : 'items'} after import?`,
        consequence:
          `Once each item below is successfully copied into your library, its source will be ` +
          `permanently deleted from this server: ${toDelete.map((e) => e.path).join(', ')}`,
        destructive: true,
      });
      if (!confirmed) return;
    }

    setBrowseImporting(true);
    for (const entry of pending) {
      setBrowseImports((prev) =>
        prev.map((e) => (e.id === entry.id ? { ...e, status: 'importing' } : e)),
      );
      try {
        const title = entry.name
          .replace(/\.[^/.]+$/, '')
          .replace(/[-_]/g, ' ')
          .trim();
        const res = await apiFetch<ImportFromPathResult>(importPath, {
          method: 'POST',
          body: JSON.stringify({
            source_path: entry.path,
            title,
            delete_original: entry.deleteOriginal,
          }),
        });
        if (res.job_id) {
          const jobId = res.job_id;
          dispatch({
            type: 'UPSERT_JOB',
            payload: {
              id: jobId,
              kind: 'upload',
              status: 'processing',
              progress: 0,
              message: `Importing "${title}"…`,
            },
          });
          // Background path: the import isn't actually finished yet, so don't
          // mark this entry successful or invalidate the cache. Instead track
          // the job's live progress (rendered below from state.backgroundJobs)
          // until it reaches a terminal state; the shared 'upload-complete'
          // window event (fired from AppContext once the job is 'done', which
          // also surfaces any delete_original_error via a toast) handles cache
          // invalidation and error reporting for this entry from here on.
          setBrowseImports((prev) =>
            prev.map((e) => (e.id === entry.id ? { ...e, status: 'processing', jobId } : e)),
          );
          continue;
        }
        // The import itself always succeeded by this point, delete_original_error
        // means only the post-import source cleanup failed. Distinct from
        // 'error': this is a partial success, not an import failure.
        if (res.delete_original_error) {
          setBrowseImports((prev) =>
            prev.map((e) =>
              e.id === entry.id ? { ...e, status: 'partial', error: res.delete_original_error } : e,
            ),
          );
        } else if (res.delete_original_note) {
          setBrowseImports((prev) =>
            prev.map((e) =>
              e.id === entry.id ? { ...e, status: 'success', note: res.delete_original_note } : e,
            ),
          );
        } else {
          setBrowseImports((prev) =>
            prev.map((e) => (e.id === entry.id ? { ...e, status: 'success' } : e)),
          );
        }
        onComplete();
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : 'Import failed.';
        setBrowseImports((prev) =>
          prev.map((e) => (e.id === entry.id ? { ...e, status: 'error', error: message } : e)),
        );
      }
    }
    setBrowseImporting(false);
  }

  const succeeded = entries.filter((e) => e.status === 'success' || e.status === 'reused').length;
  const failed = entries.filter((e) => e.status === 'error').length;
  const showSummary = entries.length > 0 && !busy;

  return (
    <>
      <Modal
        open={open}
        title={config.modalTitle}
        onClose={onClose}
        busy={dismissBlocked}
        footer={
          multiDisc ? (
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  if (setStatus === 'uploading') {
                    setAbortRef.current?.();
                  } else {
                    onClose();
                  }
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={setStatus === 'success' ? onClose : submitSet}
                disabled={
                  busy || !(folderName.trim() || discSetTitle.trim()) || stagedDiscs.length === 0
                }
              >
                {setStatus === 'uploading'
                  ? 'Creating set…'
                  : setStatus === 'success'
                    ? 'Done'
                    : 'Create Set'}
              </Button>
            </div>
          ) : folderMode ? (
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  if (folderStatus === 'uploading') {
                    folderAbortRef.current?.();
                  } else {
                    onClose();
                  }
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={folderStatus === 'success' ? onClose : submitFolderUpload}
                disabled={busy || !folderTitle.trim() || folderFiles.length === 0}
              >
                {folderStatus === 'uploading'
                  ? 'Uploading…'
                  : folderStatus === 'success'
                    ? 'Done'
                    : 'Upload Folder'}
              </Button>
            </div>
          ) : entries.some((e) => e.status === 'uploading') ? (
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  entryAbortsRef.current.forEach((abort) => abort());
                }}
              >
                Cancel
              </Button>
              <Button disabled>Uploading…</Button>
            </div>
          ) : (
            <Button onClick={onClose}>Done</Button>
          )
        }
      >
        {/* Mode toggles */}
        {(supportsMultiDisc || supportsFolderMode) && (
          <div className="mb-3 flex flex-col gap-1.5">
            {supportsMultiDisc && (
              <Checkbox
                checked={multiDisc}
                disabled={busy}
                onCheckedChange={(checked) => {
                  setMultiDisc(checked);
                  setStagedDiscs([]);
                  setDiscSetTitle('');
                  setFolderName('');
                  setFolderNameTouched(false);
                  setSetStatus('idle');
                  setSetError(null);
                  setSetBackground(false);
                  setSetJobId(null);
                }}
                label="Multi-disc set"
              />
            )}
            {supportsFolderMode && (
              <Checkbox
                checked={folderMode}
                disabled={busy}
                onCheckedChange={(checked) => {
                  setFolderMode(checked);
                  setFolderFiles([]);
                  setFolderTitle('');
                  setFolderStatus('idle');
                  setFolderError(null);
                  setFolderResult(null);
                  setFolderBackground(false);
                  setFolderJobId(null);
                }}
                label="Folder upload"
              />
            )}
          </div>
        )}

        {multiDisc ? (
          <MultiDiscMode
            busy={busy}
            folderMode={folderMode}
            acceptFileTypes={config.acceptFileTypes}
            setTitle={discSetTitle}
            onSetTitleChange={setDiscSetTitle}
            folderName={folderName}
            onFolderNameChange={(v) => {
              setFolderName(v);
              setFolderNameTouched(true);
            }}
            dragActive={dragActive}
            onDragActiveChange={setDragActive}
            onFiles={handleFiles}
            onDiscFolderPick={handleDiscFolderPick}
            stagedDiscs={stagedDiscs}
            onMoveDisc={moveDisc}
            onRemoveDisc={removeDisc}
            setStatus={setStatus}
            setError={setError}
            setProgress={setProgress}
            setBackground={setBackground}
            setJobId={setJobId}
            backgroundJobs={state.backgroundJobs}
          />
        ) : folderMode ? (
          <FolderUploadMode
            busy={busy}
            folderTitle={folderTitle}
            onFolderTitleChange={setFolderTitle}
            folderFiles={folderFiles}
            onSelectFiles={setFolderFiles}
            folderStatus={folderStatus}
            folderError={folderError}
            folderProgress={folderProgress}
            folderBackground={folderBackground}
            folderJobId={folderJobId}
            folderResult={folderResult}
            backgroundJobs={state.backgroundJobs}
          />
        ) : (
          <SingleFileMode
            accept={config.acceptFileTypes}
            dragActive={dragActive}
            onDragActiveChange={setDragActive}
            onFiles={handleFiles}
            entries={entries}
            backgroundJobs={state.backgroundJobs}
          />
        )}

        {supportsBrowseImport && !multiDisc && !folderMode && (
          <BrowseImportPanel
            busy={busy}
            libraryDefaultsLoading={libraryDefaultsLoading}
            browserOpen={browserOpen}
            onBrowserOpenChange={setBrowserOpen}
            onSelectPath={handleBrowseSelect}
            browseImports={browseImports}
            onToggleEntryDelete={toggleEntryDelete}
            onRemoveEntry={removeBrowseEntry}
            onToggleDeleteAll={toggleDeleteAllOriginal}
            onSubmit={submitBrowseImports}
            browseImporting={browseImporting}
            backgroundJobs={state.backgroundJobs}
          />
        )}

        <p className="mt-2 text-xs text-neutral-400 dark:text-neutral-500">
          {mediaPath
            ? `Tip: uploads are copied through the browser, which can be slow for very large files. For faster imports of large files, place them directly in ${mediaPath} and use Scan instead.`
            : `Tip: uploads are copied through the browser, which can be slow for very large files. Set a library path in Settings to enable faster imports of large files.`}
          {supportsBrowseImport &&
            ` Dragged/dropped or picked files can't offer to delete their source afterward, the ` +
              `browser never exposes a real file path for that input method. Use "Import from a path on ` +
              `this server" above if you want the option to delete the original after import.`}
        </p>

        {!multiDisc && !folderMode && showSummary && (
          <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
            {succeeded} of {entries.length} file{entries.length !== 1 ? 's' : ''} added successfully
            {failed > 0 && `, ${failed} failed`}.
          </p>
        )}
      </Modal>

      <ConfirmModal
        open={deleteConfirmOpen}
        title={deleteConfirmOptions?.title ?? ''}
        consequence={deleteConfirmOptions?.consequence ?? ''}
        destructive={deleteConfirmOptions?.destructive}
        onConfirm={handleDeleteConfirmed}
        onCancel={handleDeleteCancelled}
      />
    </>
  );
}
