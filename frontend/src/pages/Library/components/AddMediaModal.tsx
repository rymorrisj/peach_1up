import { useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { UploadCloud, ChevronUp, ChevronDown, X } from 'lucide-react'
import { uploadFile } from '@/lib/uploadFile'
import { getCsrfToken } from '@/api/client'
import { Button, Modal } from '@/ui'

const _BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

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

function newEntryId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

interface AddMediaModalProps {
  open: boolean
  onClose: () => void
  onAdded: () => void
  mediaPath?: string | null
}

export function AddMediaModal({ open, onClose, onAdded, mediaPath }: AddMediaModalProps) {
  const [entries, setEntries] = useState<UploadEntry[]>([])
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  // Multi-disc state
  const [multiDisc, setMultiDisc] = useState(false)
  const [stagedDiscs, setStagedDiscs] = useState<StagedDisc[]>([])
  const [setTitle, setSetTitle] = useState('')
  const [setStatus, setSetStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [setError, setSetError] = useState<string | null>(null)

  // Folder upload state
  const [folderMode, setFolderMode] = useState(false)
  const [folderFiles, setFolderFiles] = useState<File[]>([])
  const [folderTitle, setFolderTitle] = useState('')
  const [folderStatus, setFolderStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [folderError, setFolderError] = useState<string | null>(null)
  const [folderResult, setFolderResult] = useState<{ type: 'item' | 'set'; title: string; discCount?: number } | null>(null)

  const busy =
    entries.some((e) => e.status === 'uploading') ||
    setStatus === 'uploading' ||
    folderStatus === 'uploading'

  useEffect(() => {
    if (!open && !busy) {
      setEntries([])
      setStagedDiscs([])
      setSetTitle('')
      setSetStatus('idle')
      setSetError(null)
      setMultiDisc(false)
      setFolderFiles([])
      setFolderTitle('')
      setFolderStatus('idle')
      setFolderError(null)
      setFolderResult(null)
      setFolderMode(false)
    }
  }, [open, busy])

  function startUpload(entry: UploadEntry) {
    const { promise } = uploadFile<{ title: string; reused_existing_media?: boolean }>(
      '/api/v1/library/upload',
      entry.file,
      (pct) => {
        setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, progress: pct } : e)))
      },
    )
    promise
      .then((body) => {
        const status = body.reused_existing_media ? 'reused' : 'success'
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
    if (!setTitle.trim()) return
    if (stagedDiscs.length === 0) return

    setSetStatus('uploading')
    setSetError(null)

    const fd = new FormData()
    fd.append('title', setTitle.trim())
    for (const disc of stagedDiscs) fd.append('files', disc.file)

    try {
      const res = await fetch(`${_BASE_URL}/api/v1/library/sets`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': getCsrfToken() },
        credentials: 'include',
        body: fd,
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string }
        throw new Error(body.detail ?? `Upload failed (HTTP ${res.status})`)
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

    setFolderStatus('uploading')
    setFolderError(null)

    const fd = new FormData()
    fd.append('title', folderTitle.trim())
    for (const f of folderFiles) fd.append('files', f)

    try {
      const res = await fetch(`${_BASE_URL}/api/v1/library/upload-folder`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': getCsrfToken() },
        credentials: 'include',
        body: fd,
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string }
        throw new Error(body.detail ?? `Upload failed (HTTP ${res.status})`)
      }
      const body = (await res.json()) as {
        result_type: string
        title: string
        items?: unknown[]
      }
      setFolderResult(
        body.result_type === 'library_set'
          ? { type: 'set', title: body.title, discCount: body.items?.length }
          : { type: 'item', title: body.title },
      )
      setFolderStatus('success')
      onAdded()
    } catch (err) {
      setFolderStatus('error')
      setFolderError(err instanceof Error ? err.message : 'Upload failed.')
    }
  }

  const succeeded = entries.filter((e) => e.status === 'success' || e.status === 'reused').length
  const failed = entries.filter((e) => e.status === 'error').length
  const showSummary = entries.length > 0 && !busy

  return (
    <Modal
      open={open}
      title="Add Media"
      onClose={onClose}
      footer={
        folderMode ? (
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
        ) : multiDisc ? (
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
              disabled={busy || !setTitle.trim() || stagedDiscs.length === 0}
            >
              {setStatus === 'uploading' ? 'Creating set…' : setStatus === 'success' ? 'Done' : 'Create Set'}
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
              if (e.target.checked) setFolderMode(false)
              setStagedDiscs([])
              setSetTitle('')
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
              if (e.target.checked) setMultiDisc(false)
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

      {/* Folder upload UI */}
      {folderMode ? (
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
            <div className="flex items-center gap-2 text-sm text-neutral-400">
              <svg className="animate-spin h-4 w-4 shrink-0 text-[#ff8a5c]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Uploading folder…
            </div>
          )}
          {folderStatus === 'success' && folderResult && (
            <p className="text-sm text-emerald-400">
              {folderResult.type === 'set'
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
              {multiDisc ? 'Add disc files (one per disc, in order)' : 'Drag and drop files here, or click to browse'}
            </p>
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              {multiDisc
                ? 'Files will appear below — drag to reorder before creating the set.'
                : 'Multiple files are supported — each uploads and imports independently.'}
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
          {!multiDisc && entries.length > 0 && (
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

          {/* Multi-disc staged list */}
          {multiDisc && stagedDiscs.length > 0 && (
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
          {multiDisc && setStatus === 'uploading' && (
            <div className="mt-3 flex items-center gap-2 text-sm text-neutral-400">
              <svg className="animate-spin h-4 w-4 shrink-0 text-[#ff8a5c]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Uploading discs…
            </div>
          )}
          {multiDisc && setStatus === 'success' && (
            <p className="mt-3 text-sm text-emerald-400">
              Set created successfully.
            </p>
          )}
          {multiDisc && setStatus === 'error' && setError && (
            <p role="alert" className="mt-3 text-sm text-red-400">{setError}</p>
          )}
        </>
      )}

      <p className="mt-2 text-xs text-neutral-400 dark:text-neutral-500">
        {mediaPath
          ? `Tip: uploads are copied through the browser, which can be slow for very large files. For faster imports of large files, place them directly in ${mediaPath} and use Scan instead.`
          : 'Tip: uploads are copied through the browser, which can be slow for very large files. Set a media library path in Settings to enable faster imports of large files via Scan.'}
      </p>

      {!multiDisc && !folderMode && showSummary && (
        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
          {succeeded} of {entries.length} file{entries.length !== 1 ? 's' : ''} added successfully
          {failed > 0 && `, ${failed} failed`}.
        </p>
      )}
    </Modal>
  )
}
