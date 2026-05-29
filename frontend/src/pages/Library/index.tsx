import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Modal } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'
import { useConfirm } from '@/hooks/useConfirm'
import { useLibraryScan } from '@/hooks/useLibraryScan'
import { useConfirmToken } from '@/hooks/useConfirmToken'
import { ERA_LABELS } from '@/generated/constants'
import type { components } from '@shared/types'
type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

const SELECT_CLASS =
  'rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[#ff8a5c] border'

// ── Add Media modal ────────────────────────────────────────────────────────

interface AddMediaForm {
  title: string
  media_path: string
  profile_id: number | null
}

const EMPTY_ADD: AddMediaForm = { title: '', media_path: '', profile_id: null }


// ── Card design constants ──────────────────────────────────────────────────

const ERA_CHIP_LABEL: Record<string, string> = {
  dos: 'DOS', win31: 'WIN31', win95: 'WIN95', win98: 'WIN98', winxp: 'WINXP',
  ps1: 'PS1', ps2: 'PS2', xbox: 'XBOX', nes: 'NES', n64: 'N64',
  dreamcast: 'DC',
}

const ERA_PLACEHOLDER: Record<string, { bg: string; color: string }> = {
  dos:   { bg: 'linear-gradient(155deg, #2b2316 0%, #16110a 100%)', color: '#d6a64a' },
  win31: { bg: 'linear-gradient(155deg, #16292b 0%, #0a1517 100%)', color: '#4ec3c0' },
  win95: { bg: 'linear-gradient(155deg, #20281a 0%, #11160c 100%)', color: '#b6d36b' },
  win98: { bg: 'linear-gradient(155deg, #17202b 0%, #0c1118 100%)', color: '#6ea8d6' },
  winxp: { bg: 'linear-gradient(155deg, #182617 0%, #0e150d 100%)', color: '#66b27a' },
}
const DEFAULT_PLACEHOLDER = { bg: 'linear-gradient(155deg, #1c2230 0%, #11141c 100%)', color: '#6aa9d6' }

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

function isAbsolutePath(p: string) {
  return /^([A-Za-z]:[/\\]|\/)/.test(p)
}

interface AddMediaModalProps {
  open: boolean
  profiles: LaunchProfile[]
  onClose: () => void
  onAdded: () => void
  mediaRootPath?: string | null
}

function AddMediaModal({ open, profiles, onClose, onAdded, mediaRootPath }: AddMediaModalProps) {
  const [form, setForm] = useState<AddMediaForm>(EMPTY_ADD)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
      setForm(EMPTY_ADD)
      setError(null)
    }
  }, [open])

  function setField<K extends keyof AddMediaForm>(key: K, value: AddMediaForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function handleFolderPicked(folderPath: string) {
    setField('media_path', folderPath)
    if (!form.title && folderPath) {
      const folderName = folderPath.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? ''
      setField('title', folderName.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()))
    }
  }

  async function handleSubmit() {
    if (!form.media_path.trim()) {
      setError('A folder path is required.')
      return
    }
    if (!isAbsolutePath(form.media_path.trim())) {
      setError(
        'The path does not look like an absolute path. ' +
        'Browser security prevents reading the full path from the file picker — ' +
        'please type or paste the complete path (e.g. C:\\library\\media\\my-game).',
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
      <FormField
        label="Folder"
        htmlFor="add-path"
        hint="Select a folder inside your media library. Each folder is one library item."
      >
        <PathInput
          id="add-path"
          mode="folder"
          value={form.media_path}
          onChange={handleFolderPicked}
          placeholder="C:\library\media\my-game"
          className="mt-1"
          hasError={!!error && !form.media_path}
          rootPath={mediaRootPath}
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
        hint="Optional — era is auto-detected from your media, or falls back to the selected profile. You can change it from the detail view."
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

interface ScanModalProps {
  open: boolean
  onClose: () => void
  onImported: () => void
}

function ScanModal({ open, onClose, onImported }: ScanModalProps) {
  const { scanning, status, error, handleScan } = useLibraryScan({ open, onImported })

  const hasDone = status && !status.running

  return (
    <Modal
      open={open}
      title="Scan Library"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={scanning}>
            {hasDone ? 'Close' : 'Cancel'}
          </Button>
          {!hasDone && (
            <Button onClick={handleScan} loading={scanning} disabled={scanning}>
              Scan
            </Button>
          )}
        </>
      }
    >
      {scanning && (
        <div className="flex items-center gap-2 text-sm text-neutral-500">
          <LoadingSpinner label="Scanning…" />
          <span>Scanning…</span>
        </div>
      )}

      {hasDone && status.results.length === 0 && (
        <p className="text-sm text-neutral-500">No new folders found in the media library.</p>
      )}

      {hasDone && status.results.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            Imported {status.results.length} item{status.results.length !== 1 ? 's' : ''}
          </p>
          <ul className="max-h-64 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-md border border-neutral-200 dark:border-neutral-700">
            {status.results.map((r) => (
              <li key={r.folder_path} className="px-3 py-2">
                <span className="block truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {r.name}
                </span>
                <span className="block truncate text-xs text-neutral-400 dark:text-neutral-500">
                  {r.executable_path ?? 'No launchable file found'} · {r.folder_path}
                </span>
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

function ArtPlaceholder({ item }: { item: LibraryItem }) {
  const style = ERA_PLACEHOLDER[item.era] ?? DEFAULT_PLACEHOLDER
  const label = ERA_CHIP_LABEL[item.era] ?? (item.era?.toUpperCase() ?? '—')
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
      label: ERA_CHIP_LABEL[item.era] ?? item.era.toUpperCase(),
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

  const { data: settingsData } = useQuery<{ paths: { media_path: string | null } }>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
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
        profiles={profiles}
        onClose={() => setAddOpen(false)}
        onAdded={invalidate}
        mediaRootPath={settingsData?.paths?.media_path ?? null}
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
    </div>
  )
}
