import { useRef } from 'react'
import type { DragEvent } from 'react'
import { UploadCloud } from 'lucide-react'
import type { BackgroundJob } from '@/context/_AppContext'
import ProgressBar from './ProgressBar'
import type { UploadEntry } from './types'

interface SingleFileModeProps {
  accept?: string
  dragActive: boolean
  onDragActiveChange: (active: boolean) => void
  onFiles: (fileList: FileList) => void
  entries: UploadEntry[]
  backgroundJobs: BackgroundJob[]
}

export default function SingleFileMode({
  accept,
  dragActive,
  onDragActiveChange,
  onFiles,
  entries,
  backgroundJobs,
}: SingleFileModeProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    onDragActiveChange(false)
    if (e.dataTransfer.files?.length) onFiles(e.dataTransfer.files)
  }

  return (
    <>
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); onDragActiveChange(true) }}
        onDragLeave={() => onDragActiveChange(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
        className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center cursor-pointer transition-colors ${
          dragActive
            ? 'border-accent bg-accent/5'
            : 'border-neutral-300 dark:border-neutral-700 hover:border-accent/60'
        }`}
      >
        <UploadCloud size={28} className="text-neutral-400" aria-hidden="true" />
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Drag and drop files here, or click to browse
        </p>
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          Multiple files are supported, each uploads and imports independently.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={accept}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            if (e.target.files?.length) onFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {/* Single-upload progress list */}
      {entries.length > 0 && (
        <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto">
          {entries.map((entry) => {
            const liveJob = entry.jobId ? backgroundJobs.find((j) => j.id === entry.jobId) : undefined
            const finalizing = entry.status === 'success' && liveJob && liveJob.status !== 'done'
            const finalizeFailed = entry.status === 'success' && liveJob?.status === 'error'
            const finalizePct = liveJob ? Math.round((liveJob.progress ?? 0) * 100) : 0
            return (
              <li key={entry.id} className="rounded-md border border-neutral-200 dark:border-neutral-700 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm text-neutral-800 dark:text-neutral-200">
                    {entry.file.name}
                  </span>
                  <span className="shrink-0 text-xs font-medium">
                    {entry.status === 'uploading' && <span className="text-neutral-400">{entry.progress}%</span>}
                    {finalizeFailed && (
                      <span className="text-red-500" title={liveJob?.error ?? undefined}>Finalize failed</span>
                    )}
                    {!finalizeFailed && finalizing && (
                      <span className="text-neutral-400">{liveJob?.message ?? 'Finalizing…'}</span>
                    )}
                    {!finalizeFailed && !finalizing && entry.status === 'success' && (
                      <span className="text-emerald-500">✓ Added</span>
                    )}
                    {entry.status === 'reused' && <span className="text-emerald-500">✓ Reused existing file</span>}
                    {entry.status === 'error' && <span className="text-red-500">Failed</span>}
                  </span>
                </div>
                {entry.status === 'uploading' && (
                  <div className="mt-1.5">
                    <ProgressBar pct={entry.progress} />
                  </div>
                )}
                {finalizing && !finalizeFailed && (
                  <div className="mt-1.5">
                    <ProgressBar pct={finalizePct} slow />
                  </div>
                )}
                {entry.status === 'error' && entry.error && (
                  <p role="alert" className="mt-1 text-xs text-red-500">{entry.error}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}
