import { useRef } from 'react'
import type { DragEvent } from 'react'
import { UploadCloud, ChevronUp, ChevronDown, X } from 'lucide-react'
import { Input, Button } from '@/ui'
import type { BackgroundJob } from '@/context/_AppContext'
import ProgressBar from './ProgressBar'
import type { StagedDisc } from './types'

interface MultiDiscModeProps {
  busy: boolean
  folderMode: boolean
  acceptFileTypes?: string
  setTitle: string
  onSetTitleChange: (value: string) => void
  folderName: string
  onFolderNameChange: (value: string) => void
  dragActive: boolean
  onDragActiveChange: (active: boolean) => void
  onFiles: (fileList: FileList) => void
  onDiscFolderPick: (fileList: FileList) => void
  stagedDiscs: StagedDisc[]
  onMoveDisc: (id: string, dir: -1 | 1) => void
  onRemoveDisc: (id: string) => void
  setStatus: 'idle' | 'uploading' | 'success' | 'error'
  setError: string | null
  setProgress: number
  setBackground: boolean
  setJobId: string | null
  backgroundJobs: BackgroundJob[]
}

export default function MultiDiscMode({
  busy,
  folderMode,
  acceptFileTypes,
  setTitle,
  onSetTitleChange,
  folderName,
  onFolderNameChange,
  dragActive,
  onDragActiveChange,
  onFiles,
  onDiscFolderPick,
  stagedDiscs,
  onMoveDisc,
  onRemoveDisc,
  setStatus,
  setError,
  setProgress,
  setBackground,
  setJobId,
  backgroundJobs,
}: MultiDiscModeProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const discFolderInputRef = useRef<HTMLInputElement>(null)

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    onDragActiveChange(false)
    if (e.dataTransfer.files?.length) onFiles(e.dataTransfer.files)
  }

  const setJob = setJobId ? backgroundJobs.find((j) => j.id === setJobId) : undefined

  return (
    <>
      {/* When both are checked, "Folder upload" changes the input method for
          staging discs (pick per-disc folders instead of loose files) rather
          than switching to the separate single-folder auto-detect pipeline. */}
      {folderMode && (
        <p className="mb-3 text-xs text-neutral-400 dark:text-neutral-500">
          Folder upload mode: select one folder per disc below (click "Select Disc
          Folder…" once per disc, in order) instead of picking loose files.
        </p>
      )}

      <Input
        placeholder="Set title (e.g. Final Fantasy VII)"
        value={setTitle}
        onChange={(e) => onSetTitleChange(e.target.value)}
        disabled={busy}
        className="mb-3"
      />

      {/* Shared destination folder all discs are copied into. Defaults from
          the first staged disc's filename or the set title above, editable
          independently (see UploadBody's folderNameTouched effect). */}
      <Input
        placeholder="Folder name (defaults from the first disc or title)"
        value={folderName}
        onChange={(e) => onFolderNameChange(e.target.value)}
        disabled={busy}
        className="mb-3"
      />

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
            Click once per disc, in order, files inside are staged below.
          </span>
          <input
            ref={discFolderInputRef}
            type="file"
            multiple
            // @ts-expect-error webkitdirectory is not in React's InputHTMLAttributes
            webkitdirectory=""
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(e) => {
              if (e.target.files?.length) onDiscFolderPick(e.target.files)
              e.target.value = ''
            }}
          />
        </div>
      ) : (
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
            Add disc files (one per disc, in order)
          </p>
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            Files will appear below, drag to reorder before creating the set.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={acceptFileTypes}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(e) => {
              if (e.target.files?.length) onFiles(e.target.files)
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
                  onClick={() => onMoveDisc(disc.id, -1)}
                  disabled={idx === 0 || busy}
                  className="rounded p-0.5 text-neutral-500 hover:text-neutral-200 disabled:opacity-30"
                  aria-label="Move disc up"
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => onMoveDisc(disc.id, 1)}
                  disabled={idx === stagedDiscs.length - 1 || busy}
                  className="rounded p-0.5 text-neutral-500 hover:text-neutral-200 disabled:opacity-30"
                  aria-label="Move disc down"
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => onRemoveDisc(disc.id)}
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
          <ProgressBar pct={setProgress} />
        </div>
      )}
      {setStatus === 'success' && !setBackground && (
        <p className="mt-3 text-sm text-emerald-400">Set created successfully.</p>
      )}
      {setStatus === 'success' && setBackground && (() => {
        if (setJob?.status === 'error') {
          return (
            <p className="mt-3 text-sm text-red-400">
              Finalizing failed: {setJob.error ?? 'Unknown error.'}
            </p>
          )
        }
        if (setJob && setJob.status !== 'done') {
          const pct = Math.round((setJob.progress ?? 0) * 100)
          return (
            <div className="mt-3">
              <p className="text-sm text-neutral-400">{setJob.message}</p>
              <div className="mt-1">
                <ProgressBar pct={pct} slow />
              </div>
            </div>
          )
        }
        return <p className="mt-3 text-sm text-emerald-400">Set created successfully.</p>
      })()}
      {setStatus === 'error' && setError && (
        <p role="alert" className="mt-3 text-sm text-red-400">{setError}</p>
      )}
    </>
  )
}
