import { X } from 'lucide-react'
import BrowsePanel from '@/components/common/BrowsePanel'
import { Button, Checkbox } from '@/ui'
import type { BackgroundJob } from '@/context/_AppContext'
import type { BrowseImportEntry } from './types'

interface BrowseImportPanelProps {
  busy: boolean
  libraryDefaultsLoading: boolean
  browserOpen: boolean
  onBrowserOpenChange: (open: boolean) => void
  onSelectPath: (path: string, isDir: boolean) => void
  browseImports: BrowseImportEntry[]
  onToggleEntryDelete: (id: string) => void
  onRemoveEntry: (id: string) => void
  onToggleDeleteAll: () => void
  onSubmit: () => void
  browseImporting: boolean
  backgroundJobs: BackgroundJob[]
}

// The "Import from a path on this server" section of the upload body,
// independent of the drag-and-drop/file-input modes, shown alongside the
// default view only (not combined with multi-disc/folder-upload mode, which
// stage sources a different way, see UploadBody). Unlike every upload method
// above, this one knows the source's real server path, so it alone can offer
// to delete the original after a confirmed successful import. Only rendered
// when the domain config supplies an importFromPathApiPath, Media/App have no
// such route today.
export default function BrowseImportPanel({
  busy,
  libraryDefaultsLoading,
  browserOpen,
  onBrowserOpenChange,
  onSelectPath,
  browseImports,
  onToggleEntryDelete,
  onRemoveEntry,
  onToggleDeleteAll,
  onSubmit,
  browseImporting,
  backgroundJobs,
}: BrowseImportPanelProps) {
  const stagedBrowseEntries = browseImports.filter((e) => e.status === 'staged')
  const allDeleteChecked =
    stagedBrowseEntries.length > 0 && stagedBrowseEntries.every((e) => e.deleteOriginal)

  return (
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
          onClick={() => onBrowserOpenChange(!browserOpen)}
        >
          Browse Server Files…
        </Button>
      </div>
      <p className="mb-2 text-xs text-neutral-400 dark:text-neutral-500">
        Pick a file or folder already on this server, no upload needed. Click again to add more.
      </p>

      {browserOpen && (
        <div className="mb-3">
          <BrowsePanel
            open={browserOpen}
            onClose={() => onBrowserOpenChange(false)}
            onSelect={onSelectPath}
            mode="both"
            title="Select File or Folder to Import"
          />
        </div>
      )}

      {browseImports.length > 0 && (
        <>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs text-neutral-400 dark:text-neutral-500">
              {browseImports.length} staged
            </span>
            {stagedBrowseEntries.length > 0 && (
              <button
                type="button"
                onClick={onToggleDeleteAll}
                className="text-xs text-accent hover:underline"
              >
                {allDeleteChecked ? 'Uncheck All "Delete Original"' : 'Check All "Delete Original"'}
              </button>
            )}
          </div>
          <ul className="max-h-48 space-y-1.5 overflow-y-auto">
            {browseImports.map((entry) => {
              const liveJob = entry.jobId ? backgroundJobs.find((j) => j.id === entry.jobId) : undefined
              return (
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
                <Checkbox
                  checked={entry.deleteOriginal}
                  disabled={entry.status !== 'staged'}
                  onCheckedChange={() => onToggleEntryDelete(entry.id)}
                  label="Delete original"
                  size="sm"
                />
                <span className="shrink-0 text-xs font-medium">
                  {entry.status === 'importing' && <span className="text-neutral-400">Importing…</span>}
                  {entry.status === 'processing' && liveJob?.status === 'error' && (
                    <span className="text-red-500" title={liveJob.error ?? undefined}>Failed</span>
                  )}
                  {entry.status === 'processing' && liveJob?.status !== 'error' && (
                    <span className="text-neutral-400">
                      {liveJob?.message ?? 'Finalizing…'}
                      {liveJob ? ` (${Math.round((liveJob.progress ?? 0) * 100)}%)` : ''}
                    </span>
                  )}
                  {entry.status === 'success' && (
                    <span className="text-emerald-500" title={entry.note}>
                      {entry.note ? '✓ Imported in place' : '✓ Added'}
                    </span>
                  )}
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
                    onClick={() => onRemoveEntry(entry.id)}
                    aria-label={`Remove ${entry.name}`}
                    className="shrink-0 rounded p-0.5 text-neutral-400 hover:text-red-400"
                  >
                    <X size={14} />
                  </button>
                )}
              </li>
              )
            })}
          </ul>
          {stagedBrowseEntries.length > 0 && (
            <Button
              className="mt-2"
              onClick={onSubmit}
              loading={browseImporting}
              disabled={busy}
            >
              Import {stagedBrowseEntries.length} item{stagedBrowseEntries.length !== 1 ? 's' : ''}
            </Button>
          )}
        </>
      )}
    </div>
  )
}
