import { useEffect, useState } from 'react'
import { Button, Modal } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useLibraryScan } from '@/hooks/useLibraryScan'

interface ScanModalProps {
  open: boolean
  onClose: () => void
  onImported: () => void
  mediaPath?: string | null
}

export function ScanModal({ open, onClose, onImported, mediaPath }: ScanModalProps) {
  const { scanning, status, error, handleScan, importing, importResult, handleImport } =
    useLibraryScan({ open, onImported })
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const preview = status?.preview ?? []
  const hasPreview = !status?.running && !importResult && preview.length > 0
  const allSelected = preview.length > 0 && selected.size === preview.length

  // Auto-select all items when the preview first loads
  useEffect(() => {
    if (status && !status.running && !importResult && status.preview.length > 0) {
      setSelected(new Set(status.preview.map((p) => p.media_path)))
    }
  }, [status, importResult])

  useEffect(() => {
    if (!open) setSelected(new Set())
  }, [open])

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(preview.map((p) => p.media_path)))
  }

  function toggleItem(path: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const busy = scanning || importing

  return (
    <Modal
      open={open}
      title="Scan Library"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {importResult ? 'Close' : 'Cancel'}
          </Button>
          {!status && !scanning && (
            <Button onClick={handleScan} loading={scanning} disabled={scanning}>
              Scan
            </Button>
          )}
          {hasPreview && (
            <Button
              onClick={() => handleImport(Array.from(selected))}
              loading={importing}
              disabled={importing || selected.size === 0}
            >
              Import{selected.size > 0 ? ` (${selected.size})` : ''}
            </Button>
          )}
        </>
      }
    >
      {!status && !scanning && (
        <div className="space-y-2">
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            {mediaPath
              ? `Scan only looks for new files inside ${mediaPath}. Files outside this folder won't be found.`
              : 'Scan only looks for new files inside your configured media library path. Set one in Settings before scanning.'}
          </p>
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            Multi-disc games should be added manually via the{' '}
            <span className="font-medium text-neutral-500 dark:text-neutral-400">Add Media</span>{' '}
            button's multi-file checkbox. Scanning a folder of individual disc files will import
            each disc as a separate standalone item.
          </p>
        </div>
      )}

      {scanning && (
        <div className="flex items-center gap-2 text-sm text-neutral-500">
          <LoadingSpinner label="Scanning…" />
          <span>Scanning…</span>
        </div>
      )}

      {hasPreview && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              Found {preview.length} new item{preview.length !== 1 ? 's' : ''}
            </p>
            <button
              type="button"
              onClick={toggleAll}
              className="text-xs text-[#ff8a5c] hover:underline"
            >
              {allSelected ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          <ul className="max-h-64 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-md border border-neutral-200 dark:border-neutral-700">
            {preview.map((item) => (
              <li key={item.media_path} className="flex items-center gap-3 px-3 py-2">
                <input
                  type="checkbox"
                  checked={selected.has(item.media_path)}
                  onChange={() => toggleItem(item.media_path)}
                  className="h-4 w-4 shrink-0 accent-[#ff8a5c]"
                />
                <div className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                    {item.title}
                  </span>
                  <span className="block truncate text-xs text-neutral-400 dark:text-neutral-500">
                    {item.detected_era ? item.detected_era.toUpperCase() : '?'}
                    {item.is_loose && ' · loose'}
                    {item.is_zip && ' · zip'}
                    {' · '}
                    {item.media_path}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!scanning && status && preview.length === 0 && !importResult && (
        <p className="text-sm text-neutral-500">
          {status.error
            ? `Scan error: ${status.error}`
            : 'No new items found in the media library.'}
        </p>
      )}

      {importResult && (
        <div className="space-y-1">
          <p className="text-sm text-neutral-700 dark:text-neutral-300">
            Imported {importResult.imported} item{importResult.imported !== 1 ? 's' : ''}
            {importResult.skipped > 0 && `, skipped ${importResult.skipped} duplicate${importResult.skipped !== 1 ? 's' : ''}`}.
          </p>
          {importResult.errors.length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-medium text-red-500">
                {importResult.errors.length} error{importResult.errors.length !== 1 ? 's' : ''}:
              </p>
              <ul className="mt-1 max-h-32 overflow-y-auto space-y-1">
                {importResult.errors.map((e, i) => (
                  <li key={i} className="truncate text-xs text-red-400" title={e.reason}>
                    {e.path.replace(/\\/g, '/').split('/').pop()}: {e.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">❌ {error}</p>}
    </Modal>
  )
}
