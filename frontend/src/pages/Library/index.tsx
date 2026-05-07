import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Modal, PageHeader } from '@/ui'
import EraSelector, { type EraValue } from '@/components/common/EraSelector'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'
import type { LibraryItem, LaunchProfile } from '@/types'

const ERA_LABELS: Record<string, string> = {
  dos: 'DOS',
  win31: 'Windows 3.1',
  win95: 'Windows 95',
  win98: 'Windows 98',
  winxp: 'Windows XP',
  ps1: 'PlayStation 1',
  ps2: 'PlayStation 2',
  xbox: 'Original Xbox',
  nes: 'NES',
  n64: 'Nintendo 64',
}

// ── Add Media modal ────────────────────────────────────────────────────────

interface AddMediaForm {
  title: string
  media_path: string
  era: EraValue | null
}

const EMPTY_ADD: AddMediaForm = { title: '', media_path: '', era: null }

const MEDIA_ACCEPT = '.iso,.img,.cue,.chd,.xiso'

function isAbsolutePath(p: string) {
  return /^([A-Za-z]:[/\\]|\/)/.test(p)
}

interface AddMediaModalProps {
  open: boolean
  onClose: () => void
  onAdded: () => void
}

function AddMediaModal({ open, onClose, onAdded }: AddMediaModalProps) {
  const [form, setForm] = useState<AddMediaForm>(EMPTY_ADD)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    if (!open) {
      setForm(EMPTY_ADD)
      setError(null)
    }
  }, [open])

  function setField<K extends keyof AddMediaForm>(key: K, value: AddMediaForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleFilePicked(filename: string) {
    setField('media_path', filename)
    if (!form.title && filename) {
      const stem = filename.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, '') ?? ''
      setField('title', stem)
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (!file) return
    handleFilePicked(file.name)
  }

  async function handleSubmit() {
    if (!form.media_path.trim()) {
      setError('A media file path is required.')
      return
    }
    if (!isAbsolutePath(form.media_path.trim())) {
      setError(
        'The path does not look like an absolute path. ' +
        'Browser security prevents reading the full path from the file picker — ' +
        'please type or paste the complete path (e.g. C:\\Games\\mygame.iso).',
      )
      return
    }
    if (!form.title.trim()) {
      setError('A title is required.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await apiFetch('/api/v1/library', {
        method: 'POST',
        body: JSON.stringify({
          title: form.title.trim(),
          media_path: form.media_path.trim(),
          era: form.era ?? 'unknown',
        }),
      })
      onAdded()
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to add media.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title="Add Media"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submitting}>
            Add to Library
          </Button>
        </>
      }
    >
      {/* Drag-and-drop zone */}
      <div
        ref={dropRef}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex items-center justify-center rounded-lg border-2 border-dashed py-8 text-sm transition-colors ${
          dragging
            ? 'border-[#ff8a5c] bg-[#ff8a5c]/10 text-[#ff8a5c]'
            : 'border-neutral-300 text-neutral-400 dark:border-neutral-700 dark:text-neutral-500'
        }`}
      >
        Drop a media file here (.iso, .img, .cue, .chd, .xiso)
      </div>

      <FormField
        label="File Path"
        htmlFor="add-path"
        hint="Full path to the media file. Browser security limits what the picker can provide — type or paste the complete path if needed."
      >
        <PathInput
          id="add-path"
          mode="file"
          accept={MEDIA_ACCEPT}
          value={form.media_path}
          onChange={handleFilePicked}
          placeholder="C:\Games\mygame.iso"
          className="mt-1"
          hasError={!!error && !form.media_path}
        />
        {form.media_path && !isAbsolutePath(form.media_path) && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            This looks like a partial path. Please enter the complete absolute path before adding.
          </p>
        )}
      </FormField>

      <FormField label="Title" htmlFor="add-title" required>
        <Input
          id="add-title"
          value={form.title}
          onChange={(e) => setField('title', e.target.value)}
          placeholder="Game or software title"
          className="mt-1"
        />
      </FormField>

      <FormField label="Platform Era" hint="Optional — leave unset if unknown. You can assign a profile later.">
        <div className="mt-2">
          <EraSelector value={form.era} onChange={(era) => setField('era', era)} />
        </div>
        {!form.era && (
          <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            No era selected. Item will be added as "Unknown" — you can assign a profile from the detail view.
          </p>
        )}
      </FormField>

      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">❌ {error}</p>}
    </Modal>
  )
}

// ── Scan modal ─────────────────────────────────────────────────────────────

interface ScanResult {
  path: string
  era: string | null
  name: string
}

interface ScanStatus {
  running: boolean
  progress: number
  total: number
  results: ScanResult[]
}

interface ScanModalProps {
  open: boolean
  onClose: () => void
  onImported: () => void
}

function ScanModal({ open, onClose, onImported }: ScanModalProps) {
  const [directory, setDirectory] = useState('')
  const [scanning, setScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  useEffect(() => {
    if (!open) {
      setDirectory('')
      setScanning(false)
      setStatus(null)
      setSelected(new Set())
      setError(null)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [open])

  async function handleScan() {
    if (!directory.trim()) {
      setError('Enter a directory path to scan.')
      return
    }
    setError(null)
    setScanning(true)
    setStatus(null)
    try {
      await apiFetch(`/api/v1/library/scan?directory=${encodeURIComponent(directory.trim())}`, {
        method: 'POST',
      })
      pollRef.current = setInterval(async () => {
        try {
          const s = await apiFetch<ScanStatus>('/api/v1/library/scan/status')
          setStatus(s)
          if (!s.running) {
            clearInterval(pollRef.current!)
            setScanning(false)
            setSelected(new Set(s.results.map((r) => r.path)))
          }
        } catch {
          clearInterval(pollRef.current!)
          setScanning(false)
        }
      }, 1000)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Scan failed.')
      setScanning(false)
    }
  }

  async function handleImport() {
    if (!status || selected.size === 0) return
    setImporting(true)
    setError(null)
    const toImport = status.results.filter((r) => selected.has(r.path))
    let failed = 0
    for (const entry of toImport) {
      try {
        await apiFetch('/api/v1/library', {
          method: 'POST',
          body: JSON.stringify({
            title: entry.name,
            media_path: entry.path,
            era: entry.era ?? 'unknown',
          }),
        })
      } catch {
        failed++
      }
    }
    setImporting(false)
    if (failed > 0) setError(`${failed} item(s) failed to import.`)
    onImported()
    if (failed === 0) onClose()
  }

  function toggleSelect(path: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const hasDone = status && !status.running && status.results.length > 0

  return (
    <Modal
      open={open}
      title="Scan Directory"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={scanning || importing}>
            {hasDone ? 'Close' : 'Cancel'}
          </Button>
          {hasDone && (
            <Button onClick={handleImport} loading={importing} disabled={selected.size === 0}>
              Import Selected ({selected.size})
            </Button>
          )}
          {!hasDone && (
            <Button onClick={handleScan} loading={scanning} disabled={scanning}>
              Scan
            </Button>
          )}
        </>
      }
    >
      <FormField
        label="Directory"
        htmlFor="scan-dir"
        hint="Must be within your configured Images, Profiles, or ROM path."
      >
        <PathInput
          id="scan-dir"
          mode="folder"
          value={directory}
          onChange={setDirectory}
          placeholder="C:\Games"
          className="mt-1"
        />
      </FormField>

      {scanning && (
        <div className="flex items-center gap-2 text-sm text-neutral-500">
          <LoadingSpinner label="Scanning…" />
          <span>Scanning…</span>
        </div>
      )}

      {status && !status.running && status.results.length === 0 && (
        <p className="text-sm text-neutral-500">No media files found in that directory.</p>
      )}

      {hasDone && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-neutral-400 dark:text-neutral-500">
            <span>Found {status.results.length} file(s)</span>
            <button
              type="button"
              className="hover:underline"
              onClick={() =>
                setSelected(
                  selected.size === status.results.length
                    ? new Set()
                    : new Set(status.results.map((r) => r.path)),
                )
              }
            >
              {selected.size === status.results.length ? 'Deselect all' : 'Select all'}
            </button>
          </div>
          <ul className="max-h-64 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-md border border-neutral-200 dark:border-neutral-700">
            {status.results.map((r) => (
              <li key={r.path}>
                <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-neutral-50 dark:hover:bg-surface-800">
                  <input
                    type="checkbox"
                    checked={selected.has(r.path)}
                    onChange={() => toggleSelect(r.path)}
                    className="h-4 w-4 rounded"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                      {r.name}
                    </span>
                    <span className="block truncate text-xs text-neutral-400 dark:text-neutral-500">
                      {ERA_LABELS[r.era ?? ''] ?? r.era ?? 'Unknown era'} · {r.path}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">❌ {error}</p>}
    </Modal>
  )
}

// ── Library item row ───────────────────────────────────────────────────────

interface ItemRowProps {
  item: LibraryItem
  profiles: LaunchProfile[]
}

function ItemRow({ item, profiles }: ItemRowProps) {
  const profile = item.profile_id != null ? profiles.find((p) => p.id === item.profile_id) : null
  const eraLabel = ERA_LABELS[item.era] ?? (item.era === 'unknown' ? null : item.era) ?? null
  const hasProfile = profile != null

  return (
    <li className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0 flex-1">
        <Link
          to={`/library/${item.id}`}
          className="block truncate font-medium text-neutral-900 hover:text-[#ff8a5c] dark:text-neutral-100 dark:hover:text-[#ff8a5c]"
        >
          {item.title}
        </Link>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-neutral-400 dark:text-neutral-500">
          {eraLabel ? (
            <span>{eraLabel}</span>
          ) : (
            <span className="italic">Unknown era</span>
          )}
          <span>·</span>
          {hasProfile ? (
            <span className="text-neutral-600 dark:text-neutral-300">{profile.name}</span>
          ) : (
            <Link
              to={`/library/${item.id}`}
              className="text-amber-600 hover:underline dark:text-amber-400"
            >
              No profile — assign one to launch
            </Link>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {item.launch_count > 0 && (
          <span className="text-xs text-neutral-400">{item.launch_count}×</span>
        )}
        <Link to={`/library/${item.id}`}>
          <Button
            variant={hasProfile ? 'primary' : 'secondary'}
            size="sm"
            disabled={!hasProfile}
            tabIndex={-1}
          >
            {hasProfile ? 'Launch' : 'Set Profile'}
          </Button>
        </Link>
      </div>
    </li>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function Library() {
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)

  const { data: items, isLoading: itemsLoading } = useQuery<LibraryItem[]>({
    queryKey: ['library'],
    queryFn: () => apiFetch<LibraryItem[]>('/api/v1/library'),
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['library'] })
  }

  return (
    <>
      <PageHeader
        title="Library"
        description="Your media collection. Assign a profile to each item to enable launch."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setScanOpen(true)}>
              Scan Directory
            </Button>
            <Button onClick={() => setAddOpen(true)}>+ Add Media</Button>
          </div>
        }
      />

      {itemsLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading library…" />
          <span aria-hidden="true">Loading library…</span>
        </div>
      ) : !items || items.length === 0 ? (
        <EmptyState
          heading="Your library is empty"
          subtext="Add media files to get started, or scan a directory to import in bulk."
          cta={{ label: 'Add Media', onClick: () => setAddOpen(true) }}
        />
      ) : (
        <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {items.map((item) => (
            <ItemRow key={item.id} item={item} profiles={profiles} />
          ))}
        </ul>
      )}

      <AddMediaModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdded={invalidate}
      />
      <ScanModal
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onImported={invalidate}
      />
    </>
  )
}
