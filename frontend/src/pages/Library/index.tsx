import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Modal, PageHeader } from '@/ui'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'
import { useConfirm } from '@/hooks/useConfirm'
import { ERA_LABELS } from '@/generated/constants'
import type { components } from '@shared/types'
type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

const SELECT_CLASS =
  'rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100'

// ── Add Media modal ────────────────────────────────────────────────────────

interface AddMediaForm {
  title: string
  media_path: string
  profile_id: number | null
}

const EMPTY_ADD: AddMediaForm = { title: '', media_path: '', profile_id: null }

const MEDIA_ACCEPT = '.iso,.img,.cue,.chd,.xiso'

function isAbsolutePath(p: string) {
  return /^([A-Za-z]:[/\\]|\/)/.test(p)
}

interface AddMediaModalProps {
  open: boolean
  profiles: LaunchProfile[]
  onClose: () => void
  onAdded: () => void
}

function AddMediaModal({ open, profiles, onClose, onAdded }: AddMediaModalProps) {
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
      const selectedProfile = profiles.find((p) => p.id === form.profile_id) ?? null
      const body: Record<string, string | number | null> = {
        title: form.title.trim(),
        media_path: form.media_path.trim(),
        era: selectedProfile?.era ?? 'unknown',
      }
      if (form.profile_id != null) body.profile_id = form.profile_id
      await apiFetch('/api/v1/library', {
        method: 'POST',
        body: JSON.stringify(body),
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

      <FormField
        label="Launch Profile"
        htmlFor="add-profile"
        hint="Optional — era is derived from the selected profile. You can change it from the detail view."
      >
        <select
          id="add-profile"
          value={form.profile_id ?? ''}
          onChange={(e) => setField('profile_id', e.target.value ? Number(e.target.value) : null)}
          className={`mt-1 w-full ${SELECT_CLASS}`}
        >
          <option value="">— No profile (add now, assign later) —</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}{p.is_bundled ? ' (default)' : ''}
            </option>
          ))}
        </select>
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

// ── Library card ───────────────────────────────────────────────────────────

interface ItemCardProps {
  item: LibraryItem
  profiles: LaunchProfile[]
  onDelete: (item: LibraryItem) => void
}

function ItemCard({ item, profiles, onDelete }: ItemCardProps) {
  const profile = item.profile_id != null ? profiles.find((p) => p.id === item.profile_id) : null
  const eraLabel = ERA_LABELS[item.era] ?? (item.era === 'unknown' ? 'Unknown era' : item.era)
  const detailHref = `/library/${item.slug ?? item.id}`

  return (
    <div className="flex flex-col rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-700 dark:bg-surface-800">
      <div className="mb-4 min-h-[4rem] flex-1">
        <h3 className="truncate font-medium text-neutral-900 dark:text-neutral-100">
          {item.title}
        </h3>
        <p className="mt-0.5 text-xs text-neutral-400 dark:text-neutral-500">{eraLabel}</p>
        {profile ? (
          <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-300">{profile.name}</p>
        ) : (
          <p className="mt-1 text-xs font-medium text-amber-600 dark:text-amber-400">No profile</p>
        )}
      </div>
      <div className="flex gap-2">
        <Link to={detailHref} className="flex-1">
          <Button
            variant={profile ? 'primary' : 'secondary'}
            size="sm"
            className="w-full justify-center"
            tabIndex={-1}
          >
            Open
          </Button>
        </Link>
        <Button variant="destructive" size="sm" onClick={() => onDelete(item)}>
          Delete
        </Button>
      </div>
    </div>
  )
}

// ── Filters ────────────────────────────────────────────────────────────────

interface Filters {
  era: string
  profileFilter: 'all' | 'assigned' | 'unassigned'
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function Library() {
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)
  const [filters, setFilters] = useState<Filters>({ era: '', profileFilter: 'all' })
  const { confirm, isOpen: confirmOpen, options: confirmOptions, handleConfirm, handleCancel } = useConfirm()

  const { data: items, isLoading: itemsLoading } = useQuery<LibraryItem[]>({
    queryKey: ['library'],
    queryFn: () => apiFetch<LibraryItem[]>('/api/v1/library'),
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const filteredItems = (items ?? []).filter((item) => {
    if (filters.era && item.era !== filters.era) return false
    if (filters.profileFilter === 'assigned' && item.profile_id === null) return false
    if (filters.profileFilter === 'unassigned' && item.profile_id !== null) return false
    return true
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['library'] })
  }

  async function handleDelete(item: LibraryItem) {
    const confirmed = await confirm({
      title: `Delete "${item.title}"?`,
      consequence: 'This removes the item from your library. The media file on disk is not deleted.',
      destructive: true,
    })
    if (!confirmed) return
    try {
      const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(
        `/api/v1/library/${item.id}/confirm-delete`,
        { method: 'POST' },
      )
      await apiFetch(
        `/api/v1/library/${item.id}?confirmation_token=${encodeURIComponent(confirmation_token)}`,
        { method: 'DELETE' },
      )
      queryClient.invalidateQueries({ queryKey: ['library'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Delete failed.'
      alert(msg)
    }
  }

  const hasActiveFilters = filters.era !== '' || filters.profileFilter !== 'all'

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
        <>
          {/* Filter bar */}
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <select
              value={filters.era}
              onChange={(e) => setFilters((f) => ({ ...f, era: e.target.value }))}
              className={SELECT_CLASS}
            >
              <option value="">All eras</option>
              {ERA_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <select
              value={filters.profileFilter}
              onChange={(e) =>
                setFilters((f) => ({ ...f, profileFilter: e.target.value as Filters['profileFilter'] }))
              }
              className={SELECT_CLASS}
            >
              <option value="all">All items</option>
              <option value="assigned">Profile assigned</option>
              <option value="unassigned">No profile</option>
            </select>
            {hasActiveFilters && (
              <button
                type="button"
                onClick={() => setFilters({ era: '', profileFilter: 'all' })}
                className="text-xs text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
              >
                Clear filters
              </button>
            )}
            <span className="ml-auto text-xs text-neutral-400 dark:text-neutral-500">
              {filteredItems.length} of {items.length}
            </span>
          </div>

          {filteredItems.length === 0 ? (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              No items match the current filters.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredItems.map((item) => (
                <ItemCard
                  key={item.id}
                  item={item}
                  profiles={profiles}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </>
      )}

      <AddMediaModal
        open={addOpen}
        profiles={profiles}
        onClose={() => setAddOpen(false)}
        onAdded={invalidate}
      />
      <ScanModal
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onImported={invalidate}
      />
      <ConfirmModal
        open={confirmOpen}
        title={confirmOptions?.title ?? ''}
        consequence={confirmOptions?.consequence ?? ''}
        destructive={confirmOptions?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  )
}
