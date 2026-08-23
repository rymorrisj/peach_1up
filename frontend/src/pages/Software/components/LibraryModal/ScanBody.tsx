import { useState } from 'react';
import { useLibraryScan } from '@/hooks/useLibraryScan';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { Button, Modal, Checkbox } from '@/ui';
import type { LibraryModalProps } from './types';

export default function ScanBody({
  open,
  onClose,
  onComplete,
  mediaPath,
  config,
}: LibraryModalProps) {
  const {
    scanning,
    status,
    error,
    handleScan,
    handleCancelScan,
    cancelling,
    importing,
    importResult,
    handleImport,
    scanProgress,
    scanMessage,
    activeJobId,
  } = useLibraryScan({ open, onImported: onComplete });
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const preview = status?.preview ?? [];
  const hasPreview = !status?.running && !importResult && preview.length > 0;
  const allSelected = preview.length > 0 && selected.size === preview.length;

  // Auto-select all items when the preview first loads. Adjusted during
  // render (tracking previous status/importResult) rather than in a
  // useEffect: a plain local setState reacting to values that only change
  // when useLibraryScan hands back a new preview, matching the old effect's
  // [status, importResult] deps.
  const [prevAutoSelect, setPrevAutoSelect] = useState({ status, importResult });
  if (status !== prevAutoSelect.status || importResult !== prevAutoSelect.importResult) {
    setPrevAutoSelect({ status, importResult });
    if (status && !status.running && !importResult && status.preview.length > 0) {
      setSelected(new Set(status.preview.map((p) => p.file_path)));
    }
  }

  // Resets the selection whenever the modal closes. Adjusted during render
  // (tracking previous `open`) rather than in a useEffect: without the
  // transition guard, an unconditional `setSelected(new Set())` on every
  // render while closed would create a new Set reference each time and loop.
  const [prevOpenForSelection, setPrevOpenForSelection] = useState(open);
  if (open !== prevOpenForSelection) {
    setPrevOpenForSelection(open);
    if (!open) setSelected(new Set());
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(preview.map((p) => p.file_path)));
  }

  function toggleItem(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  // Blocks Modal's own dismiss paths (Escape/overlay/Dialog.Close) only
  // while there's an operation with nothing yet tracking it server-side.
  // Once activeJobId exists, the scan continues as a tracked background job
  // regardless of this modal's open state, so dismissing is safe. importing
  // has no job/background tracking at all (see useLibraryScan's top-of-file
  // comment, it's a single synchronous request), so it keeps blocking for
  // its full duration, there's nothing to fall back on if dismissed early.
  const busy = (scanning && !activeJobId) || importing;

  return (
    <Modal
      open={open}
      title={config.modalTitle}
      onClose={onClose}
      busy={busy}
      footer={
        <>
          {scanning && (
            <Button
              variant="ghost"
              onClick={handleCancelScan}
              loading={cancelling}
              disabled={cancelling}
            >
              {cancelling ? 'Cancelling…' : 'Cancel Scan'}
            </Button>
          )}
          {/* Once activeJobId exists, Escape/overlay now dismiss on their own
              (busy above has already dropped), making the 'Hide' wording here
              redundant as a bypass. Kept anyway: this same button slot is the
              genuine primary Cancel/Close action in the other two states, and
              a labeled, always-visible "Hide" is more discoverable than
              Escape/backdrop-click for a scan that can run for minutes. */}
          <Button variant="ghost" onClick={onClose} disabled={importing}>
            {importResult ? 'Close' : scanning ? 'Hide' : 'Cancel'}
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
              : 'Scan only looks for new files inside your configured library path. Set one in Settings before scanning.'}
          </p>
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            Multi-disc {config.entityLabelPlural} should be added manually via the{' '}
            <span className="font-medium text-neutral-500 dark:text-neutral-400">Add Media</span>{' '}
            button's multi-file checkbox. Scanning a folder of individual disc files will import
            each disc as a separate standalone item.
          </p>
        </div>
      )}

      {scanning && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <LoadingSpinner label="Scanning…" />
            <span>{scanMessage ?? 'Scanning…'}</span>
          </div>
          {scanProgress > 0 && (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
              <div
                className="h-full rounded-full bg-accent transition-all duration-300"
                style={{ width: `${scanProgress}%` }}
              />
            </div>
          )}
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
              className="text-xs text-accent hover:underline"
            >
              {allSelected ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          <ul className="max-h-64 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-md border border-neutral-200 dark:border-neutral-700">
            {preview.map((item) => (
              <li key={item.file_path} className="flex items-center gap-3 px-3 py-2">
                <Checkbox
                  checked={selected.has(item.file_path)}
                  onCheckedChange={() => toggleItem(item.file_path)}
                  className="shrink-0"
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
                    {item.file_path}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!scanning && status && preview.length === 0 && !importResult && (
        <p className="text-sm text-neutral-500">
          {status.cancelled
            ? 'Scan cancelled.'
            : status.error
              ? `Scan error: ${status.error}`
              : `No new items found in the ${config.entityLabelPlural} library.`}
        </p>
      )}

      {importResult && (
        <div className="space-y-1">
          <p className="text-sm text-neutral-700 dark:text-neutral-300">
            Imported {importResult.imported} item{importResult.imported !== 1 ? 's' : ''}
            {importResult.skipped > 0 &&
              `, skipped ${importResult.skipped} duplicate${importResult.skipped !== 1 ? 's' : ''}`}
            .
          </p>
          {importResult.errors.length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-medium text-red-500">
                {importResult.errors.length} error{importResult.errors.length !== 1 ? 's' : ''}:
              </p>
              <ul className="mt-1 max-h-40 overflow-y-auto space-y-1">
                {importResult.errors.map((e, i) => (
                  <li key={i} className="break-words text-xs text-red-400">
                    {e.path.replace(/\\/g, '/').split('/').pop()}: {e.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </Modal>
  );
}
