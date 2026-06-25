import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { ERA_LABEL, ERA_PLACEHOLDER, ERA_PLACEHOLDER_DEFAULT } from '@/types/era'
import type { components } from '@shared/types'

type LibraryItem = components['schemas']['LibraryItemRead']
type LaunchProfile = components['schemas']['ProfileRead']

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

interface ItemCardProps {
  item: LibraryItem
  profiles: LaunchProfile[]
  onRemove: (item: LibraryItem) => void
}

export function ItemCard({ item, profiles, onRemove }: ItemCardProps) {
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

      {/* Remove — hover-revealed, outside Link to avoid navigation */}
      <button
        type="button"
        onClick={() => onRemove(item)}
        className="absolute right-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-transparent bg-black/70 text-neutral-400 opacity-0 backdrop-blur-sm transition-opacity duration-[120ms] group-hover:opacity-100 hover:border-red-500/40 hover:text-red-400"
        aria-label={`Remove ${item.title}`}
      >
        <Trash2 size={14} />
      </button>
    </div>
  )
}
