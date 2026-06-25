import { Trash2, Disc3 } from 'lucide-react'
import { ERA_LABEL, ERA_PLACEHOLDER, ERA_PLACEHOLDER_DEFAULT } from '@/types/era'

export interface LibrarySetItemData {
  id: number
  set_id: number
  disc_number: number
  media_path: string
  cover_art_path: string | null
  cover_art_url: string | null
  executable_path: string | null
  file_size_bytes: number | null
}

export interface LibrarySetData {
  id: number
  title: string
  sort_title: string | null
  era: string
  category: string | null
  description: string | null
  publisher: string | null
  year: number | null
  content_rating: string | null
  requires_install: boolean
  launch_review_flagged: boolean
  platform_id: number | null
  profile_id: number | null
  drive_id: number | null
  launch_disk_id: number | null
  last_launched_at: string | null
  launch_count: number
  created_at: string
  updated_at: string
  items: LibrarySetItemData[]
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

function ArtPlaceholder({ set }: { set: LibrarySetData }) {
  const style = ERA_PLACEHOLDER[set.era] ?? ERA_PLACEHOLDER_DEFAULT
  const label = ERA_LABEL[set.era] ?? (set.era?.toUpperCase() ?? '—')
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
        {set.year && <span className="font-mono text-[10px] text-neutral-500">{set.year}</span>}
      </div>
      <div className="mt-auto">
        <p
          className="font-sans text-[15px] font-semibold leading-snug tracking-tight text-neutral-100"
          style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}
        >
          {set.title}
        </p>
        {set.publisher && (
          <p className="mt-1 truncate font-mono text-[10px] tracking-[0.04em] text-neutral-500">
            {set.publisher}
          </p>
        )}
      </div>
    </div>
  )
}

interface SetCardProps {
  set: LibrarySetData
  onRemove?: (set: LibrarySetData) => void
}

export function SetCard({ set, onRemove }: SetCardProps) {
  const launchDisc = set.items.find((d) => d.id === set.launch_disk_id) ?? set.items[0]
  const hasCoverArt = !!launchDisc?.cover_art_url
  const discCount = set.items.length
  const ratingCls = set.content_rating
    ? (RATING_BADGE[set.content_rating] ?? 'text-neutral-300 border-neutral-600/40')
    : null

  return (
    <div className="group relative flex flex-col gap-2.5">
      <div className="flex flex-col gap-2.5 rounded-xl">
        {/* 16:9 art area */}
        <div className="relative aspect-video overflow-hidden rounded-xl border border-transparent bg-surface-800 shadow-[0_1px_2px_rgb(20_12_6/0.4)] transition-[transform,box-shadow] duration-200 ease-out group-hover:-translate-y-0.5 group-hover:shadow-[0_4px_12px_rgb(20_12_6/0.45)]">
          {hasCoverArt ? (
            <img
              src={launchDisc!.cover_art_url!}
              alt={set.title}
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <ArtPlaceholder set={set} />
          )}

          {/* Multi-disc badge */}
          <div className="absolute left-2 top-2 z-10 flex items-center gap-1 rounded-[4px] border border-white/10 bg-black/70 px-1.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-neutral-300 backdrop-blur-sm">
            <Disc3 size={10} aria-hidden="true" />
            <span>{discCount} disc{discCount !== 1 ? 's' : ''}</span>
          </div>

          {ratingCls && (
            <div className={`absolute bottom-2 right-2 z-10 inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-[4px] border bg-black/[0.78] px-[7px] font-mono text-[11px] font-bold uppercase tracking-[0.04em] backdrop-blur-[6px] ${ratingCls}`}>
              {set.content_rating}
            </div>
          )}

          {/* Disc strip — visible on hover */}
          {discCount > 1 && (
            <div className="absolute bottom-0 left-0 right-0 z-10 flex gap-1 overflow-x-auto bg-gradient-to-t from-black/80 to-transparent px-2 pb-2 pt-4 opacity-0 transition-opacity duration-[180ms] ease-out group-hover:opacity-100">
              {set.items
                .slice()
                .sort((a, b) => a.disc_number - b.disc_number)
                .map((disc) => (
                  <div
                    key={disc.id}
                    className={`shrink-0 rounded border font-mono text-[9px] px-1.5 py-0.5 ${
                      disc.id === set.launch_disk_id
                        ? 'border-[#ff8a5c]/60 text-[#ff8a5c]/90 bg-[#ff8a5c]/10'
                        : 'border-neutral-700 text-neutral-400 bg-black/40'
                    }`}
                  >
                    {disc.disc_number}
                  </div>
                ))}
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

        {/* Title + era pill */}
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="min-w-0 flex-1 truncate font-sans text-sm font-semibold tracking-tight text-neutral-100">
            {set.title}
          </span>
          {set.era && set.era !== 'unknown' && (
            <span className="shrink-0 inline-flex items-center rounded-[4px] border border-[#ff8a5c]/40 bg-[#ff8a5c]/10 px-[7px] py-1 font-mono text-[10.5px] font-medium leading-none text-[#ff8a5c]/80 tracking-[0.08em]">
              {ERA_LABEL[set.era] ?? set.era.toUpperCase()}
            </span>
          )}
        </div>
      </div>

      {/* Remove — hover-revealed, outside the card body to avoid navigation issues */}
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(set)}
          className="absolute right-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-transparent bg-black/70 text-neutral-400 opacity-0 backdrop-blur-sm transition-opacity duration-[120ms] group-hover:opacity-100 hover:border-red-500/40 hover:text-red-400"
          aria-label={`Remove ${set.title}`}
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  )
}
