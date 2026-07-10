import { useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UploadCloud, ChevronUp, ChevronDown, X } from 'lucide-react'
import { chunkedUpload } from '@/lib/chunkedUpload'
import { apiFetch, ApiError } from '@/api/client'
import { useAppContext } from '@/context/useAppContext'
import { useConfirm } from '@/hooks/useConfirm'
import ConfirmModal from '@/components/common/ConfirmModal'
import FileBrowser from '@/components/common/FileBrowser'
import { Button, Modal } from '@/ui'

interface UploadEntry {
  id: string
  file: File
  progress: number
  status: 'uploading' | 'success' | 'reused' | 'error'
  error?: string
}

interface StagedDisc {
  id: string
  file: File
}

// A file or folder picked via the server-side file browser (real, absolute,
// server-resolved path — never a browser File object), staged for import
// via POST /api/v1/software/import-from-path. Unlike the drag-and-drop/file-
// input entries above, these can offer "delete original after import"
// because the backend already knows the source's real path.
interface BrowseImportEntry {
  id: string
  path: string
  name: string
  isDir: boolean
  deleteOriginal: boolean
  status: 'staged' | 'importing' | 'success' | 'partial' | 'error'
  error?: string
}

// Shape of the inline (non-background) response body from
// POST /api/v1/software/import-from-path — see path_import.import_inline /
// finalize_reassembled. delete_original_error is only ever present when
// delete_original was true and the post-import cleanup failed; its presence
// never means the import itself failed (the collection/item was already
// committed by that point).
interface ImportFromPathResult {
  job_id?: string
  result_type?: string
  id?: number
  title?: string
  reused_existing_media?: boolean
  disc_count?: number
  delete_original_error?: string
}

function newEntryId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// Immediate containing folder of a file picked via a `webkitdirectory` input
// (falls back to the file's own stem if no relative path is available, e.g.
// a plain file input).
function folderNameFor(file: File): string {
  const relPath = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath
  if (!relPath) return file.name.replace(/\.[^/.]+$/, '')
  const parts = relPath.split('/')
  return parts.length >= 2 ? parts[parts.length - 2] : parts[0]
}

// Recursively-picked folder(s) commonly reuse companion filenames per disc
// (e.g. every disc folder has its own "track.bin"), which would collide once
// flattened into one destination directory on the server. Original filenames
// aren't needed downstream (only executable_path/disc_number matter once
// ingested), so discard them entirely and rename from the containing folder
// instead: "{folder}{ext}" when a folder contributes one file of that
// extension, "{folder}_{n}{ext}" when it contributes more than one. This is a
// candidate name only — the existing sanitize_filename()/slugify() call in
// chunked_uploads.init_session() slugifies it server-side, so no frontend
// slugify is introduced here. Order is untouched: callers must still append
// the returned discs in the same order as the source FileList.
function stageFolderFiles(fileList: FileList): StagedDisc[] {
  const files = Array.from(fileList)
  const groupKeys = files.map((file) => {
    const folder = folderNameFor(file)
    const dot = file.name.lastIndexOf('.')
    const ext = dot >= 0 ? file.name.slice(dot) : ''
    return { folder, ext, key: `${folder}::${ext}` }
  })
  const groupIndices = new Map<string, number[]>()
  groupKeys.forEach(({ key }, i) => {
    const indices = groupIndices.get(key) ?? []
    indices.push(i)
    groupIndices.set(key, indices)
  })

  return files.map((file, i) => {
    const { folder, ext, key } = groupKeys[i]
    const indices = groupIndices.get(key)!
    const candidateName =
      indices.length > 1 ? `${folder}_${indices.indexOf(i) + 1}${ext}` : `${folder}${ext}`
    const renamed = new File([file], candidateName, { type: file.type })
    return { id: newEntryId(), file: renamed }
  })
}

interface AddMediaModalProps {
  open: boolean
  onClose: () => void
  onAdded: () => void
  mediaPath?: string | null
}

export function AddMediaModal({ open, onClose, onAdded, mediaPath }: AddMediaModalProps) {
  const { dispatch } = useAppContext()
  const [entries, setEntries] = useState<UploadEntry[]>([])
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const discFolderInputRef = useRef<HTMLInputElement>(null)

  // Multi-disc state
  const [multiDisc, setMultiDisc] = useState(false)
  const [stagedDiscs, setStagedDiscs] = useState<StagedDisc[]>([])
  const [setTitle, setSetTitle] = useState('')
  const [folderName, setFolderName] = useState('')
  const [folderNameTouched, setFolderNameTouched] = useState(false)
  const [setStatus, setSetStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [setError, setSetError] = useState<string | null>(null)
  const [setProgress, setSetProgress] = useState(0)
  const [setBackground, setSetBackground] = useState(false)

  // Folder upload state
  const [folderMode, setFolderMode] = useState(false)
  const [folderFiles, setFolderFiles] = useState<File[]>([])
  const [folderTitle, setFolderTitle] = useState('')
  const [folderStatus, setFolderStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [folderError, setFolderError] = useState<string | null>(null)
  const [folderProgress, setFolderProgress] = useState(0)
  const [folderBackground, setFolderBackground] = useState(false)
  const [folderResult, setFolderResult] = useState<{ type: 'item' | 'set'; title: string; discCount?: number } | null>(null)

  // Server-side-path import state — a second, independent source mechanism
  // alongside drag-and-drop/file-input above. Sourced via FileBrowser (real,
  // absolute, server-resolved paths), not a browser File object, so unlike
  // every other entry list in this modal it can offer "delete original".
  const [browserOpen, setBrowserOpen] = useState(false)
  const [browseImports, setBrowseImports] = useState<BrowseImportEntry[]>([])
  const [browseImporting, setBrowseImporting] = useState(false)
  const {
    confirm: confirmDeleteOriginal,
    isOpen: deleteConfirmOpen,
    options: deleteConfirmOptions,
    handleConfirm: handleDeleteConfirmed,
    handleCancel: handleDeleteCancelled,
  } = useConfirm()

  const { data: libraryDefaults, isLoading: libraryDefaultsLoading } = useQuery<{ delete_media_on_removal: boolean; delete_original_on_upload: boolean }>({
    queryKey: ['settings', 'library-defaults'],
    queryFn: () => apiFetch('/api/v1/settings/library-defaults'),
    staleTime: 60_000,
    enabled: open,
  })
  const deleteOriginalDefault = Boolean(libraryDefaults?.delete_original_on_upload)

  const busy =
    entries.some((e) => e.status === 'uploading') ||
    setStatus === 'uploading' ||
    folderStatus === 'uploading' ||
    browseImporting

  useEffect(() => {
    if (!open && !busy) {
      setEntries([])
      setStagedDiscs([])
      setSetTitle('')
      setFolderName('')
      setFolderNameTouched(false)
      setSetStatus('idle')
      setSetError(null)
      setSetProgress(0)
      setSetBackground(false)
      setMultiDisc(false)
      setFolderFiles([])
      setFolderTitle('')
      setFolderStatus('idle')
      setFolderError(null)
      setFolderProgress(0)
      setFolderBackground(false)
      setFolderResult(null)
      setFolderMode(false)
      setBrowseImports([])
      setBrowserOpen(false)
    }
  }, [open, busy])

  // Default the folder-name field from the first staged disc's filename (or
  // the set title, if no disc is staged yet) until the user edits it directly.
  useEffect(() => {
    if (folderNameTouched) return
    if (stagedDiscs.length > 0) {
      setFolderName(stagedDiscs[0].file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ').trim())
    } else if (setTitle.trim()) {
      setFolderName(setTitle.trim())
    }
  }, [stagedDiscs, setTitle, folderNameTouched])

  function startUpload(entry: UploadEntry) {
    const title = entry.file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ').trim()
    const { promise } = chunkedUpload('file', title, [entry.file], (pct) => {
      setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, progress: pct } : e)))
    })
    promise
      .then((res) => {
        // Over the server threshold: finalize runs as a background job surfaced
        // in the nav bell. The item appears in the grid once that job finishes.
        if (res.status === 202 && res.body.job_id) {
          dispatch({
            type: 'UPSERT_JOB',
            payload: { id: res.body.job_id, kind: 'upload', status: 'processing', progress: 0, message: `Finalizing "${title}"…` },
          })
          setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, status: 'success', progress: 100 } : e)))
          return
        }
        const status = res.body.reused_existing_media ? 'reused' : 'success'
        setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, status, progress: 100 } : e)))
        onAdded()
      })
      .catch((err: Error) => {
        setEntries((prev) =>
          prev.map((e) => (e.id === entry.id ? { ...e, status: 'error', error: err.message } : e)),
        )
      })
  }

  function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList)
    if (files.length === 0) return

    if (multiDisc) {
      setStagedDiscs((prev) => [
        ...prev,
        ...files.map((f) => ({ id: newEntryId(), file: f })),
      ])
      return
    }

    const next: UploadEntry[] = files.map((file) => ({
      id: newEntryId(),
      file,
      progress: 0,
      status: 'uploading',
    }))
    setEntries((prev) => [...prev, ...next])
    next.forEach(startUpload)
  }

  // Multi-disc + folder-upload combo: the picked folder's files are already
  // recursively enumerated by the browser (webkitdirectory walks the whole
  // tree), so this just renames for collision-safety and appends — no new
  // recursion logic, and append order is preserved (= upload order).
  function handleDiscFolderPick(fileList: FileList) {
    if (fileList.length === 0) return
    setStagedDiscs((prev) => [...prev, ...stageFolderFiles(fileList)])
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragActive(false)
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files)
  }

  function moveDisc(id: string, dir: -1 | 1) {
    setStagedDiscs((prev) => {
      const idx = prev.findIndex((d) => d.id === id)
      if (idx < 0) return prev
      const next = [...prev]
      const swap = idx + dir
      if (swap < 0 || swap >= next.length) return prev
      ;[next[idx], next[swap]] = [next[swap], next[idx]]
      return next
    })
  }

  function removeDisc(id: string) {
    setStagedDiscs((prev) => prev.filter((d) => d.id !== id))
  }

  async function submitSet() {
    const title = folderName.trim() || setTitle.trim()
    if (!title) return
    if (stagedDiscs.length === 0) return

    setSetStatus('uploading')
    setSetError(null)
    setSetProgress(0)
    setSetBackground(false)

    const { promise } = chunkedUpload('set', title, stagedDiscs.map((d) => d.file), setSetProgress)
    try {
      const res = await promise
      if (res.status === 202 && res.body.job_id) {
        dispatch({
          type: 'UPSERT_JOB',
          payload: { id: res.body.job_id, kind: 'upload', status: 'processing', progress: 0, message: `Finalizing "${title}"…` },
        })
        setSetBackground(true)
        setSetStatus('success')
        return
      }
      setSetStatus('success')
      onAdded()
    } catch (err) {
      setSetStatus('error')
      setSetError(err instanceof Error ? err.message : 'Upload failed.')
    }
  }

  async function submitFolderUpload() {
    if (!folderTitle.trim() || folderFiles.length === 0) return

    const title = folderTitle.trim()
    setFolderStatus('uploading')
    setFolderError(null)
    setFolderProgress(0)
    setFolderBackground(false)

    const { promise } = chunkedUpload('folder', title, folderFiles, setFolderProgress)
    try {
      const res = await promise
      if (res.status === 202 && res.body.job_id) {
        dispatch({
          type: 'UPSERT_JOB',
          payload: { id: res.body.job_id, kind: 'upload', status: 'processing', progress: 0, message: `Finalizing "${title}"…` },
        })
        setFolderBackground(true)
        setFolderResult({ type: 'item', title })
        setFolderStatus('success')
        return
      }
      setFolderResult(
        (res.body.disc_count ?? 1) > 1
          ? { type: 'set', title: res.body.title ?? title, discCount: res.body.disc_count }
          : { type: 'item', title: res.body.title ?? title },
      )
      setFolderStatus('success')
      onAdded()
    } catch (err) {
      setFolderStatus('error')
      setFolderError(err instanceof Error ? err.message : 'Upload failed.')
    }
  }

  // Each Browse click appends one entry — FileBrowser is single-select, so
  // staging multiple sources means clicking "Browse Server Files…" once per
  // item, mirroring how "Select Disc Folder…" above is clicked once per disc.
  function handleBrowseSelect(path: string, isDir: boolean) {
    const name = path.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? path
    setBrowseImports((prev) => [
      ...prev,
      { id: newEntryId(), path, name, isDir, deleteOriginal: deleteOriginalDefault, status: 'staged' },
    ])
  }

  function toggleEntryDelete(id: string) {
    setBrowseImports((prev) =>
      prev.map((e) => (e.id === id ? { ...e, deleteOriginal: !e.deleteOriginal } : e)),
    )
  }

  function removeBrowseEntry(id: string) {
    setBrowseImports((prev) => prev.filter((e) => e.id !== id))
  }

  const stagedBrowseEntries = browseImports.filter((e) => e.status === 'staged')
  const allDeleteChecked =
    stagedBrowseEntries.length > 0 && stagedBrowseEntries.every((e) => e.deleteOriginal)

  // Mirrors ScanModal's toggleAll/allSelected pattern exactly, applied to
  // deleteOriginal instead of an import-selection set — every staged entry is
  // always imported here, so there's no separate "select which to import"
  // step the way Scan's preview has.
  function toggleDeleteAllOriginal() {
    const next = !allDeleteChecked
    setBrowseImports((prev) =>
      prev.map((e) => (e.status === 'staged' ? { ...e, deleteOriginal: next } : e)),
    )
  }

  async function submitBrowseImports() {
    const pending = browseImports.filter((e) => e.status === 'staged')
    if (pending.length === 0) return

    const toDelete = pending.filter((e) => e.deleteOriginal)
    if (toDelete.length > 0) {
      const confirmed = await confirmDeleteOriginal({
        title: `Delete ${toDelete.length} original ${toDelete.length === 1 ? 'item' : 'items'} after import?`,
        consequence:
          `Once each item below is successfully copied into your library, its source will be ` +
          `permanently deleted from this server: ${toDelete.map((e) => e.path).join(', ')}`,
        destructive: true,
      })
      if (!confirmed) return
    }

    setBrowseImporting(true)
    for (const entry of pending) {
      setBrowseImports((prev) => prev.map((e) => (e.id === entry.id ? { ...e, status: 'importing' } : e)))
      try {
        const title = entry.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ').trim()
        const res = await apiFetch<ImportFromPathResult>('/api/v1/software/import-from-path', {
          method: 'POST',
          body: JSON.stringify({ source_path: entry.path, title, delete_original: entry.deleteOriginal }),
        })
        if (res.job_id) {
          dispatch({
            type: 'UPSERT_JOB',
            payload: { id: res.job_id, kind: 'upload', status: 'processing', progress: 0, message: `Importing "${title}"…` },
          })
        }
        // The import itself always succeeded by this point — delete_original_error
        // (inline path only; res.job_id means this went to the background path
        // instead, surfaced separately via the job consumer in AppContext) means
        // only the post-import source cleanup failed. Distinct from 'error' —
        // this is a partial success, not an import failure.
        if (res.delete_original_error) {
          setBrowseImports((prev) => prev.map((e) =>
            e.id === entry.id ? { ...e, status: 'partial', error: res.delete_original_error } : e,
          ))
        } else {
          setBrowseImports((prev) => prev.map((e) => (e.id === entry.id ? { ...e, status: 'success' } : e)))
        }
        onAdded()
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : 'Import failed.'
        setBrowseImports((prev) => prev.map((e) => (e.id === entry.id ? { ...e, status: 'error', error: message } : e)))
      }
    }
    setBrowseImporting(false)
  }

  const succeeded = entries.filter((e) => e.status === 'success' || e.status === 'reused').length
  const failed = entries.filter((e) => e.status === 'error').length
  const showSummary = entries.length > 0 && !busy

  return (
    <>
    <Modal
      open={open}
      title="Add Media"
      onClose={onClose}
      busy={busy}
      footer={
        multiDisc ? (
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              onClick={setStatus === 'success' ? onClose : submitSet}
              disabled={busy || !(folderName.trim() || setTitle.trim()) || stagedDiscs.length === 0}
            >
              {setStatus === 'uploading' ? 'Creating set…' : setStatus === 'success' ? 'Done' : 'Create Set'}
            </Button>
          </div>
        ) : folderMode ? (
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onClose} disabled={busy}>
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
        ) : (
          <Button onClick={onClose}>
            {busy ? 'Upload in progress…' : 'Done'}
          </Button>
        )
      }
    >
      {/* Mode toggles */}
      <div className="mb-3 flex flex-col gap-1.5">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-neutral-300">
          <input
            type="checkbox"
            className="accent-[#ff8a5c]"
            checked={multiDisc}
            disabled={busy}
            onChange={(e) => {
              setMultiDisc(e.target.checked)
              setStagedDiscs([])
              setSetTitle('')
              setFolderName('')
              setFolderNameTouched(false)
              setSetStatus('idle')
              setSetError(null)
            }}
          />
          Multi-disc set
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-neutral-300">
          <input
            type="checkbox"
            className="accent-[#ff8a5c]"
            checked={folderMode}
            disabled={busy}
            onChange={(e) => {
              setFolderMode(e.target.checked)
              setFolderFiles([])
              setFolderTitle('')
              setFolderStatus('idle')
              setFolderError(null)
              setFolderResult(null)
            }}
          />
          Folder upload
        </label>
      </div>

      {/* When both are checked, "Folder upload" changes the input method for
          staging discs (pick per-disc folders instead of loose files) rather
          than switching to the separate single-folder auto-detect pipeline. */}
      {multiDisc && folderMode && (
        <p className="mb-3 text-xs text-neutral-400 dark:text-neutral-500">
          Folder upload mode: select one folder per disc below (click "Select Disc
          Folder…" once per disc, in order) instead of picking loose files.
        </p>
      )}

      {/* Set title field (multi-disc mode only) */}
      {multiDisc && (
        <input
          type="text"
          placeholder="Set title (e.g. Final Fantasy VII)"
          value={setTitle}
          onChange={(e) => setSetTitle(e.target.value)}
          disabled={busy}
          className="mb-3 w-full rounded-lg border border-neutral-600 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:border-[#ff8a5c]"
        />
      )}

      {/* Folder name field (multi-disc mode only) — the shared destination
          folder all discs are copied into. Defaults from the first staged
          disc's filename or the set title above, editable independently. */}
      {multiDisc && (
        <input
          type="text"
          placeholder="Folder name (defaults from the first disc or title)"
          value={folderName}
          onChange={(e) => {
            setFolderName(e.target.value)
            setFolderNameTouched(true)
          }}
          disabled={busy}
          className="mb-3 w-full rounded-lg border border-neutral-600 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:border-[#ff8a5c]"
        />
      )}

      {multiDisc ? (
        <>
          {/* Disc input: a folder picker (one click per disc) when "Folder
              upload" is also checked, otherwise the flat multi-file picker. */}
          {folderMode ? (
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => discFolderInputRef.current?.click()}
              >
                Select Disc Folder…
              </Button>
              <span className="text-xs text-neutral-400">
                Click once per disc, in order — files inside are staged below.
              </span>
              {/* @ts-expect-error webkitdirectory is not in React's InputHTMLAttributes */}
              <input
                ref={discFolderInputRef}
                type="file"
                multiple
                webkitdirectory=""
                className="sr-only"
                tabIndex={-1}
                aria-hidden="true"
                onChange={(e) => {
                  if (e.target.files?.length) handleDiscFolderPick(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>
          ) : (
            <div
              onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
              className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center cursor-pointer transition-colors ${
                dragActive
                  ? 'border-[#ff8a5c] bg-[#ff8a5c]/5'
                  : 'border-neutral-300 dark:border-neutral-700 hover:border-[#ff8a5c]/60'
              }`}
            >
              <UploadCloud size={28} className="text-neutral-400" aria-hidden="true" />
              <p className="text-sm text-neutral-600 dark:text-neutral-300">
                Add disc files (one per disc, in order)
              </p>
              <p className="text-xs text-neutral-400 dark:text-neutral-500">
                Files will appear below — drag to reorder before creating the set.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="sr-only"
                tabIndex={-1}
                aria-hidden="true"
                onChange={(e) => {
                  if (e.target.files?.length) handleFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>
          )}

          {/* Multi-disc staged list */}
          {stagedDiscs.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {stagedDiscs.map((disc, idx) => (
                <li
                  key={disc.id}
                  className="flex items-center gap-2 rounded-md border border-neutral-700 bg-neutral-800/60 px-3 py-2"
                >
                  <span className="w-5 shrink-0 font-mono text-xs text-neutral-500">{idx + 1}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-neutral-200">{disc.file.name}</span>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => moveDisc(disc.id, -1)}
                      disabled={idx === 0 || busy}
                      className="rounded p-0.5 text-neutral-500 hover:text-neutral-200 disabled:opacity-30"
                      aria-label="Move disc up"
                    >
                      <ChevronUp size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveDisc(disc.id, 1)}
                      disabled={idx === stagedDiscs.length - 1 || busy}
                      className="rounded p-0.5 text-neutral-500 hover:text-neutral-200 disabled:opacity-30"
                      aria-label="Move disc down"
                    >
                      <ChevronDown size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeDisc(disc.id)}
                      disabled={busy}
                      className="rounded p-0.5 text-neutral-500 hover:text-red-400 disabled:opacity-30"
                      aria-label={`Remove ${disc.file.name}`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {/* Set upload status */}
          {setStatus === 'uploading' && (
            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between text-xs text-neutral-400">
                <span>Uploading discs…</span>
                <span>{setProgress}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
                <div className="h-full rounded-full bg-[#ff8a5c] transition-all duration-100" style={{ width: `${setProgress}%` }} />
              </div>
            </div>
          )}
          {setStatus === 'success' && (
            <p className="mt-3 text-sm text-emerald-400">
              {setBackground
                ? 'Upload complete — the set is being finalized in the background. Track it in the Activity panel.'
                : 'Set created successfully.'}
            </p>
          )}
          {setStatus === 'error' && setError && (
            <p role="alert" className="mt-3 text-sm text-red-400">{setError}</p>
          )}
        </>
      ) : folderMode ? (
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Title (e.g. Sonic Adventure)"
            value={folderTitle}
            onChange={(e) => setFolderTitle(e.target.value)}
            disabled={busy}
            className="w-full rounded-lg border border-neutral-600 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:border-[#ff8a5c]"
          />
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => folderInputRef.current?.click()}
            >
              Select Folder…
            </Button>
            {folderFiles.length > 0 && (
              <span className="text-sm text-neutral-400">
                {folderFiles.length} file{folderFiles.length !== 1 ? 's' : ''} selected
              </span>
            )}
            {/* @ts-expect-error webkitdirectory is not in React's InputHTMLAttributes */}
            <input
              ref={folderInputRef}
              type="file"
              multiple
              webkitdirectory=""
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={(e) => {
                if (e.target.files?.length) setFolderFiles(Array.from(e.target.files))
                e.target.value = ''
              }}
            />
          </div>
          {folderFiles.length > 0 && (
            <ul className="max-h-40 space-y-1 overflow-y-auto">
              {folderFiles.map((f, i) => (
                <li
                  key={i}
                  className="truncate rounded px-2 py-0.5 font-mono text-xs text-neutral-400"
                >
                  {f.name}
                </li>
              ))}
            </ul>
          )}
          {folderStatus === 'uploading' && (
            <div>
              <div className="mb-1 flex items-center justify-between text-xs text-neutral-400">
                <span>Uploading folder…</span>
                <span>{folderProgress}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
                <div className="h-full rounded-full bg-[#ff8a5c] transition-all duration-100" style={{ width: `${folderProgress}%` }} />
              </div>
            </div>
          )}
          {folderStatus === 'success' && folderResult && (
            <p className="text-sm text-emerald-400">
              {folderBackground
                ? `Upload complete — "${folderResult.title}" is being finalized in the background. Track it in the Activity panel.`
                : folderResult.type === 'set'
                ? `Added "${folderResult.title}" as a ${folderResult.discCount}-disc set.`
                : `Added "${folderResult.title}" as a library item.`}
            </p>
          )}
          {folderStatus === 'error' && folderError && (
            <p role="alert" className="text-sm text-red-400">{folderError}</p>
          )}
        </div>
      ) : (
        <>
          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
            className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center cursor-pointer transition-colors ${
              dragActive
                ? 'border-[#ff8a5c] bg-[#ff8a5c]/5'
                : 'border-neutral-300 dark:border-neutral-700 hover:border-[#ff8a5c]/60'
            }`}
          >
            <UploadCloud size={28} className="text-neutral-400" aria-hidden="true" />
            <p className="text-sm text-neutral-600 dark:text-neutral-300">
              Drag and drop files here, or click to browse
            </p>
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              Multiple files are supported — each uploads and imports independently.
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={(e) => {
                if (e.target.files?.length) handleFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          {/* Single-upload progress list */}
          {entries.length > 0 && (
            <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto">
              {entries.map((entry) => (
                <li key={entry.id} className="rounded-md border border-neutral-200 dark:border-neutral-700 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm text-neutral-800 dark:text-neutral-200">
                      {entry.file.name}
                    </span>
                    <span className="shrink-0 text-xs font-medium">
                      {entry.status === 'uploading' && <span className="text-neutral-400">{entry.progress}%</span>}
                      {entry.status === 'success' && <span className="text-emerald-500">✓ Added</span>}
                      {entry.status === 'reused' && <span className="text-emerald-500">✓ Reused existing file</span>}
                      {entry.status === 'error' && <span className="text-red-500">Failed</span>}
                    </span>
                  </div>
                  {entry.status === 'uploading' && (
                    <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
                      <div
                        className="h-full rounded-full bg-[#ff8a5c] transition-all duration-100"
                        style={{ width: `${entry.progress}%` }}
                      />
                    </div>
                  )}
                  {entry.status === 'error' && entry.error && (
                    <p role="alert" className="mt-1 text-xs text-red-500">{entry.error}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {/* Server-side-path import — independent of the drag-and-drop/file-input
          modes above, so it's shown alongside the default view only (not
          combined with multi-disc/folder-upload mode, which stage sources a
          different way). Unlike every method above, this one knows the
          source's real server path, so it alone can offer to delete the
          original after a confirmed successful import. */}
      {!multiDisc && !folderMode && (
        <div className="mt-4 border-t border-neutral-200 pt-4 dark:border-neutral-700">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Import from a path on this server
            </p>
            <Button
              variant="secondary"
              size="sm"
              disabled={busy || libraryDefaultsLoading}
              loading={libraryDefaultsLoading}
              onClick={() => setBrowserOpen(true)}
            >
              Browse Server Files…
            </Button>
          </div>
          <p className="mb-2 text-xs text-neutral-400 dark:text-neutral-500">
            Pick a file or folder already on this server — no upload needed. Click again to add more.
          </p>

          {browseImports.length > 0 && (
            <>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {browseImports.length} staged
                </span>
                {stagedBrowseEntries.length > 0 && (
                  <button
                    type="button"
                    onClick={toggleDeleteAllOriginal}
                    className="text-xs text-[#ff8a5c] hover:underline"
                  >
                    {allDeleteChecked ? 'Uncheck All "Delete Original"' : 'Check All "Delete Original"'}
                  </button>
                )}
              </div>
              <ul className="max-h-48 space-y-1.5 overflow-y-auto">
                {browseImports.map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-center gap-2 rounded-md border border-neutral-200 dark:border-neutral-700 px-3 py-2"
                  >
                    <span
                      className="min-w-0 flex-1 truncate text-sm text-neutral-800 dark:text-neutral-200"
                      title={entry.path}
                    >
                      {entry.isDir ? '📁' : '📄'} {entry.name}
                    </span>
                    <label className="flex shrink-0 items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
                      <input
                        type="checkbox"
                        checked={entry.deleteOriginal}
                        disabled={entry.status !== 'staged'}
                        onChange={() => toggleEntryDelete(entry.id)}
                        className="h-3.5 w-3.5"
                      />
                      Delete original
                    </label>
                    <span className="shrink-0 text-xs font-medium">
                      {entry.status === 'importing' && <span className="text-neutral-400">Importing…</span>}
                      {entry.status === 'success' && <span className="text-emerald-500">✓ Added</span>}
                      {entry.status === 'partial' && (
                        <span className="text-amber-500" title={entry.error}>
                          ✓ Added, original not deleted
                        </span>
                      )}
                      {entry.status === 'error' && <span className="text-red-500" title={entry.error}>Failed</span>}
                    </span>
                    {entry.status === 'staged' && (
                      <button
                        type="button"
                        onClick={() => removeBrowseEntry(entry.id)}
                        aria-label={`Remove ${entry.name}`}
                        className="shrink-0 rounded p-0.5 text-neutral-400 hover:text-red-400"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {stagedBrowseEntries.length > 0 && (
                <Button
                  className="mt-2"
                  onClick={submitBrowseImports}
                  loading={browseImporting}
                  disabled={busy}
                >
                  Import {stagedBrowseEntries.length} item{stagedBrowseEntries.length !== 1 ? 's' : ''}
                </Button>
              )}
            </>
          )}
        </div>
      )}

      <p className="mt-2 text-xs text-neutral-400 dark:text-neutral-500">
        {mediaPath
          ? `Tip: uploads are copied through the browser, which can be slow for very large files. For faster imports of large files, place them directly in ${mediaPath} and use Scan instead.`
          : 'Tip: uploads are copied through the browser, which can be slow for very large files. Set a software library path in Settings to enable faster imports of large files via Scan.'}
        {' '}Dragged/dropped or picked files can't offer to delete their source afterward — the
        browser never exposes a real file path for that input method. Use "Import from a path on
        this server" above if you want the option to delete the original after import.
      </p>

      {!multiDisc && !folderMode && showSummary && (
        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
          {succeeded} of {entries.length} file{entries.length !== 1 ? 's' : ''} added successfully
          {failed > 0 && `, ${failed} failed`}.
        </p>
      )}
    </Modal>

    <FileBrowser
      open={browserOpen}
      onClose={() => setBrowserOpen(false)}
      onSelect={handleBrowseSelect}
      mode="both"
      title="Select File or Folder to Import"
    />

    <ConfirmModal
      open={deleteConfirmOpen}
      title={deleteConfirmOptions?.title ?? ''}
      consequence={deleteConfirmOptions?.consequence ?? ''}
      destructive={deleteConfirmOptions?.destructive}
      onConfirm={handleDeleteConfirmed}
      onCancel={handleDeleteCancelled}
    />
    </>
  )
}
