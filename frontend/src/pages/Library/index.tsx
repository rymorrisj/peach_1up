import { useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Trash2, UploadCloud } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { uploadFile } from '@/lib/uploadFile'
import { Button, Modal } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import { useLibraryScan } from '@/hooks/useLibraryScan'
import { useConfirmToken } from '@/hooks/useConfirmToken'
import { ERA_LABELS } from '@/generated/constants'
import { ERA_LABEL, ERA_PLACEHOLDER, ERA_PLACEHOLDER_DEFAULT } from '@/types/era'
import type { components } from '@shared/types'
type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

const SELECT_CLASS =
  'rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[#ff8a5c] border'

interface ResolvedPaths {
  library_path: string | null
  media_path: string | null
}

// ── Add Media modal ────────────────────────────────────────────────────────

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

const RATING_BADGE: Record<string, string> = {
  EC:        'text-emerald-300 border-emerald-500/40',
  E:         'text-emerald-300 border-emerald-500/40',
  'E10+':    'text-emerald-300 border-emerald-500/40',
  T:         'text-amber-300 border-amber-500/40',
  M:         'text-red-300 border-red-400/45',
  AO:        'text-red-300 border-red-400/55',
  'PEGI 3':  'text-emerald-300 border-emerald-500/40',
  'PEGI 7':  'text-emerald-300 border-emerald-500/40',
  'PEGI 12': 'text-emerald-300 border-emerald-500/40',
  'PEGI 16': 'text-amber-300 border-amber-500/40',
  'PEGI 18': 'text-red-300 border-red-400/55',
}

interface AddMediaModalProps {
  open: boolean
  onClose: () => void
  onAdded: () => void
  mediaPath?: string | null
}

function AddMediaModal({ open, onClose, onAdded, mediaPath }: AddMediaModalProps) {
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

// ── Scan modal ─────────────────────────────────────────────────────────────

interface ScanModalProps {
  open: boolean
  onClose: () => void
  onImported: () => void
  mediaPath?: string | null
}

function ScanModal({ open, onClose, onImported, mediaPath }: ScanModalProps) {
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
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          {mediaPath
            ? `Scan only looks for new files inside ${mediaPath}. Files outside this folder won't be found.`
            : 'Scan only looks for new files inside your configured media library path. Set one in Settings before scanning.'}
        </p>
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

// ── Library card ───────────────────────────────────────────────────────────

interface ItemCardProps {
  item: LibraryItem
  profiles: LaunchProfile[]
  onDelete: (item: LibraryItem) => void
}

function ArtPlaceholder({ item }: { item: LibraryItem }) {
  const style = ERA_PLACEHOLDER[item.era] ?? ERA_PLACEHOLDER_DEFAULT
  const label = ERA_LABEL[item.era] ?? (item.era?.toUpperCase() ?? '—')
  return (
    <div
      className="absolute inset-0 flex flex-col overflow-hidden p-3.5"
      style={{ background: style.bg, color: style.color }}
    >
      <div className="absolute bottom-0 left-0 top-0 w-[5px]" style={{ background: 'currentColor' }} />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, transparent 0 7px, currentColor 7px 8px),' +
            'repeating-linear-gradient(90deg, transparent 0 7px, currentColor 7px 8px)',
        }}
      />
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]">{label}</span>
        {item.year && <span className="font-mono text-[10px] text-neutral-500">{item.year}</span>}
      </div>
      <div className="mt-auto">
        <p
          className="font-sans text-[15px] font-semibold leading-snug tracking-tight text-neutral-100"
          style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}
        >
          {item.title}
        </p>
        {item.publisher && (
          <p className="mt-1 truncate font-mono text-[10px] tracking-[0.04em] text-neutral-500">
            {item.publisher}
          </p>
        )}
      </div>
    </div>
  )
}

function TagPills({ item }: { item: LibraryItem }) {
  type Pill = { label: string; cls: string }
  const pills: Pill[] = []
  if (item.era && item.era !== 'unknown') {
    pills.push({
      label: ERA_LABEL[item.era] ?? item.era.toUpperCase(),
      cls: 'border-[#ff8a5c]/40 bg-[#ff8a5c]/10 text-[#ff8a5c]/80 tracking-[0.08em]',
    })
  }
  if (item.category) {
    pills.push({
      label: item.category,
      cls: 'border-blue-500/40 bg-blue-500/10 text-blue-300',
    })
  }
  const visible = pills.slice(0, 3)
  const extra = pills.length - visible.length
  if (!visible.length) return null
  return (
    <div className="flex flex-nowrap gap-1.5 overflow-hidden">
      {visible.map((p, i) => (
        <span key={i} className={`inline-flex shrink-0 items-center rounded-[4px] border px-[7px] py-1 font-mono text-[10.5px] font-medium leading-none ${p.cls}`}>
          {p.label}
        </span>
      ))}
      {extra > 0 && (
        <span className="inline-flex shrink-0 items-center rounded-[4px] border border-neutral-700 px-[7px] py-1 font-mono text-[10.5px] leading-none text-neutral-500">
          +{extra}
        </span>
      )}
    </div>
  )
}

function ItemCard({ item, profiles, onDelete }: ItemCardProps) {
  const profile = item.profile_id != null ? profiles.find((p) => p.id === item.profile_id) : null
  const detailHref = `/library/${item.slug ?? item.id}`
  const hasCoverArt = !!item.cover_art_url
  const ratingCls = item.content_rating
    ? (RATING_BADGE[item.content_rating] ?? 'text-neutral-300 border-neutral-600/40')
    : null

  return (
    <div className="group relative flex flex-col gap-2.5">
      <Link
        to={detailHref}
        className="flex flex-col gap-2.5 rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff8a5c] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950"
      >
        {/* 16:9 art area */}
        <div className="relative aspect-video overflow-hidden rounded-xl border border-transparent bg-surface-800 shadow-[0_1px_2px_rgb(20_12_6/0.4)] transition-[transform,box-shadow] duration-200 ease-out group-hover:-translate-y-0.5 group-hover:shadow-[0_4px_12px_rgb(20_12_6/0.45)]">
          {hasCoverArt ? (
            <img
              src={item.cover_art_url!}
              alt={item.title}
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <ArtPlaceholder item={item} />
          )}

          {!profile && (
            <div className="absolute left-2 top-2 z-10 rounded-[4px] border border-white/10 bg-black/70 px-1.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-neutral-400 backdrop-blur-sm">
              No profile
            </div>
          )}

          {ratingCls && (
            <div className={`absolute bottom-2 right-2 z-10 inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-[4px] border bg-black/[0.78] px-[7px] font-mono text-[11px] font-bold uppercase tracking-[0.04em] backdrop-blur-[6px] ${ratingCls}`}>
              {item.content_rating}
            </div>
          )}

          {/* Hover overlay — play button */}
          <div
            className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-[180ms] ease-out group-hover:opacity-100"
            aria-hidden="true"
            style={{ background: 'linear-gradient(180deg, rgb(13 16 20 / 0) 30%, rgb(13 16 20 / 0.55) 100%)' }}
          >
            <div className="flex h-[52px] w-[52px] scale-[0.82] items-center justify-center rounded-full bg-[#ff8a5c] text-[#1d0a04] shadow-[0_6px_18px_rgb(20_12_6/0.55),0_0_0_1px_rgb(255_255_255/0.08)_inset] transition-transform duration-200 ease-out group-hover:scale-100">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M5 3.5v13l11-6.5z" />
              </svg>
            </div>
          </div>
        </div>

        {/* Title */}
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="min-w-0 flex-1 truncate font-sans text-sm font-semibold tracking-tight text-neutral-100">
            {item.title}
          </span>
          {profile && (
            <span className="shrink-0 text-xs text-emerald-400" aria-label="profile assigned">✓</span>
          )}
        </div>

        {/* Tag pills */}
        <TagPills item={item} />
      </Link>

      {/* Delete — hover-revealed, outside Link to avoid navigation */}
      <button
        type="button"
        onClick={() => onDelete(item)}
        className="absolute right-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-transparent bg-black/70 text-neutral-400 opacity-0 backdrop-blur-sm transition-opacity duration-[120ms] group-hover:opacity-100 hover:border-red-500/40 hover:text-red-400"
        aria-label={`Delete ${item.title}`}
      >
        <Trash2 size={14} />
      </button>
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
  const [searchParams, setSearchParams] = useSearchParams()
  const [addOpen, setAddOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)
  const [filters, setFilters] = useState<Filters>({ era: searchParams.get('era') ?? '', profileFilter: 'all' })

  useEffect(() => {
    setFilters((f) => ({ ...f, era: searchParams.get('era') ?? '' }))
  }, [searchParams])
  const { confirm, isOpen: confirmOpen, options: confirmOptions, handleConfirm, handleCancel } = useConfirm()
  const { issue: issueToken, consume: consumeToken } = useConfirmToken()

  const { data: items, isLoading: itemsLoading } = useQuery<LibraryItem[]>({
    queryKey: ['library'],
    queryFn: () => apiFetch<LibraryItem[]>('/api/v1/library'),
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: settingsData } = useQuery<{ paths: ResolvedPaths }>({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch('/api/v1/settings/first-run-status'),
    staleTime: 60_000,
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
      const token = await issueToken(`/api/v1/library/${item.id}/confirm-delete`)
      await consumeToken(`/api/v1/library/${item.id}`, token)
      queryClient.invalidateQueries({ queryKey: ['library'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Delete failed.'
      alert(msg)
    }
  }

  const hasActiveFilters = filters.era !== '' || filters.profileFilter !== 'all'

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Library">
        <span style={{ flex: 1 }} />
        <Button variant="secondary" onClick={() => setScanOpen(true)}>
          Scan Directory
        </Button>
        <Button onClick={() => setAddOpen(true)}>+ Add Media</Button>
      </TopBar>

      <div className="p-6">
        {itemsLoading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg-3)' }}>
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
                onChange={(e) => {
                  const v = e.target.value
                  setFilters((f) => ({ ...f, era: v }))
                  setSearchParams((p) => { if (v) p.set('era', v); else p.delete('era'); return p })
                }}
                className={SELECT_CLASS}
                style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
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
                style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
              >
                <option value="all">All items</option>
                <option value="assigned">Profile assigned</option>
                <option value="unassigned">No profile</option>
              </select>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={() => {
                    setFilters({ era: '', profileFilter: 'all' })
                    setSearchParams((p) => { p.delete('era'); return p })
                  }}
                  style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--fg-3)', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  Clear filters
                </button>
              )}
              <span className="ml-auto" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                {filteredItems.length} of {items.length}
              </span>
            </div>

            {filteredItems.length === 0 ? (
              <p style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: 'var(--fg-3)' }}>
                No items match the current filters.
              </p>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
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
      </div>

      <AddMediaModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdded={invalidate}
        mediaPath={settingsData?.paths?.media_path ?? null}
      />
      <ScanModal
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onImported={invalidate}
        mediaPath={settingsData?.paths?.media_path ?? null}
      />
      <ConfirmModal
        open={confirmOpen}
        title={confirmOptions?.title ?? ''}
        consequence={confirmOptions?.consequence ?? ''}
        destructive={confirmOptions?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  )
}
