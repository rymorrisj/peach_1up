import { useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { UploadCloud } from 'lucide-react'
import { uploadFile } from '@/lib/uploadFile'
import { Button, Modal } from '@/ui'

interface UploadEntry {
  id: string
  file: File
  progress: number
  status: 'uploading' | 'success' | 'error'
  error?: string
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

  const busy = entries.some((e) => e.status === 'uploading')

  useEffect(() => {
    if (!open && !busy) {
      setEntries([])
    }
  }, [open, busy])

  function startUpload(entry: UploadEntry) {
    const { promise } = uploadFile<{ title: string }>('/api/v1/library/upload', entry.file, (pct) => {
      setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, progress: pct } : e)))
    })
    promise
      .then(() => {
        setEntries((prev) => prev.map((e) => (e.id === entry.id ? { ...e, status: 'success', progress: 100 } : e)))
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

  const succeeded = entries.filter((e) => e.status === 'success').length
  const failed = entries.filter((e) => e.status === 'error').length
  const showSummary = entries.length > 0 && !busy

  return (
    <Modal
      open={open}
      title="Add Media"
      onClose={onClose}
      footer={
        <Button onClick={onClose}>
          {busy ? 'Upload in progress…' : 'Done'}
        </Button>
      }
    >
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

      <p className="mt-2 text-xs text-neutral-400 dark:text-neutral-500">
        {mediaPath
          ? `Tip: uploads are copied through the browser, which can be slow for very large files. For faster imports of large files, place them directly in ${mediaPath} and use Scan instead.`
          : 'Tip: uploads are copied through the browser, which can be slow for very large files. Set a media library path in Settings to enable faster imports of large files via Scan.'}
      </p>

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

      {showSummary && (
        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
          {succeeded} of {entries.length} file{entries.length !== 1 ? 's' : ''} added successfully
          {failed > 0 && `, ${failed} failed`}.
        </p>
      )}
    </Modal>
  )
}
