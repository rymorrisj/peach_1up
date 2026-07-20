import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'

interface DriveEntry {
  letter: string
  path: string
  label: string
}

interface DirEntry {
  name: string
  path: string
}

interface FileEntry {
  name: string
  path: string
  size_bytes: number
}

interface BrowseResult {
  current_path: string | null
  parent_path: string | null
  dirs: DirEntry[]
  files: FileEntry[]
}

interface BrowsePanelProps {
  open: boolean
  onClose: () => void
  // isDir reflects which listing produced the selection (the folder-select
  // button vs. a row from `files`), callers that only care about the path
  // can ignore the second argument.
  onSelect: (path: string, isDir: boolean) => void
  extensions?: string
  title?: string
  mode?: 'file' | 'folder' | 'both'
  rootPath?: string | null
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

// Renders the server-side filesystem browser as plain in-content DOM, a
// normal descendant of whatever parent is already showing it (a Modal's
// Dialog.Content, or a page section), never a second top-layer dialog. This
// matters because a native <dialog> rendered as a sibling of a Radix
// Dialog.Content defeats Radix's outside-interaction detection (some event
// types find the dialog via `event.target.closest('dialog')`, others don't),
// which previously caused clicks inside the browser to intermittently close
// the parent modal underneath it. Being a real descendant sidesteps the
// problem entirely instead of guarding each Radix event type individually.
export default function BrowsePanel({
  open,
  onClose,
  onSelect,
  extensions,
  title = 'Browse',
  mode = 'file',
  rootPath,
}: BrowsePanelProps) {
  const [currentPath, setCurrentPath] = useState<string | null>(rootPath ?? null)

  useEffect(() => {
    if (open) setCurrentPath(rootPath ?? null)
  }, [open, rootPath])

  const { data: drivesData } = useQuery({
    queryKey: ['filesystem', 'drives'],
    queryFn: async () => {
      try {
        return await apiFetch<{ drives: DriveEntry[] }>('/api/v1/filesystem/drives')
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null
        throw err
      }
    },
    enabled: open,
    staleTime: 60_000,
  })

  const showFiles = mode === 'file' || mode === 'both'

  const { data: browseData, isLoading, error } = useQuery<BrowseResult>({
    queryKey: ['filesystem', 'browse', currentPath, extensions, showFiles],
    queryFn: () => {
      const p = new URLSearchParams()
      if (currentPath) p.set('path', currentPath)
      if (extensions) p.set('extensions', extensions)
      p.set('show_files', String(showFiles))
      return apiFetch<BrowseResult>(`/api/v1/filesystem/browse?${p}`)
    },
    enabled: open,
    gcTime: 0,
  })

  if (!open) return null

  function handleSelectFolder() {
    if (currentPath) {
      onSelect(currentPath, true)
      onClose()
    }
  }

  return (
    <div className="w-full rounded-lg border border-border-strong bg-surface-1 p-4">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{title}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close browser"
          className="rounded p-1 text-neutral-400 hover:bg-surface-2 hover:text-neutral-600 dark:hover:text-neutral-200"
        >
          ✕
        </button>
      </div>

      {/* Navigation bar */}
      {currentPath ? (
        <div className="mb-3 flex items-center gap-2">
          {(!rootPath || currentPath !== rootPath) && (
            <button
              type="button"
              onClick={() =>
                setCurrentPath(browseData?.parent_path ?? rootPath ?? null)
              }
              className="shrink-0 text-xs text-accent hover:underline"
            >
              ← Back
            </button>
          )}
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">
            {currentPath}
          </span>
          {(mode === 'folder' || mode === 'both') && (
            <Button size="sm" onClick={handleSelectFolder} className="shrink-0">
              Select this folder
            </Button>
          )}
        </div>
      ) : (
        <p className="mb-3 text-xs text-neutral-400 dark:text-neutral-500">
          Choose a starting location
        </p>
      )}

      {/* Drive picker (Windows only, home view, hidden when scoped to a rootPath) */}
      {!currentPath && !rootPath && drivesData?.drives && drivesData.drives.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            Drives
          </p>
          <div className="flex flex-wrap gap-2">
            {drivesData.drives.map((d) => (
              <button
                key={d.letter}
                type="button"
                onClick={() => setCurrentPath(d.path)}
                className="rounded-md border border-neutral-200 bg-surface-2 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-surface-3 dark:border-neutral-700 dark:text-neutral-300"
              >
                {d.label}
              </button>
            ))}
          </div>
          <div className="mb-3 mt-3 border-t border-neutral-100 dark:border-neutral-800" />
        </div>
      )}

      {/* Directory listing */}
      <div className="max-h-72 min-h-[10rem] overflow-y-auto rounded-md border border-neutral-200 dark:border-neutral-700">
        {isLoading && (
          <div className="flex items-center justify-center p-8">
            <LoadingSpinner label="Loading…" />
          </div>
        )}

        {error && (
          <p className="p-4 text-sm text-red-600 dark:text-red-400">
            ❌{' '}
            {error instanceof ApiError
              ? error.detail
              : 'Failed to load directory.'}
          </p>
        )}

        {!isLoading && !error && browseData && (
          <>
            {browseData.dirs.length === 0 && browseData.files.length === 0 && (
              <p className="p-4 text-sm text-neutral-400 dark:text-neutral-500">
                This directory is empty.
              </p>
            )}
            <ul>
              {browseData.dirs.map((d) => (
                <li key={d.path} className="border-b border-neutral-100 last:border-0 dark:border-neutral-800">
                  <button
                    type="button"
                    onClick={() => setCurrentPath(d.path)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2"
                  >
                    <span aria-hidden="true" className="shrink-0 text-neutral-400">📁</span>
                    <span className="truncate text-neutral-900 dark:text-neutral-100">{d.name}</span>
                  </button>
                </li>
              ))}
              {browseData.files.map((f) => (
                <li key={f.path} className="border-b border-neutral-100 last:border-0 dark:border-neutral-800">
                  <button
                    type="button"
                    onClick={() => { onSelect(f.path, false); onClose() }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2"
                  >
                    <span aria-hidden="true" className="shrink-0 text-neutral-400">📄</span>
                    <span className="min-w-0 flex-1 truncate text-neutral-900 dark:text-neutral-100">{f.name}</span>
                    <span className="shrink-0 text-xs text-neutral-400 dark:text-neutral-500">
                      {formatSize(f.size_bytes)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="mt-4 flex justify-end">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  )
}
