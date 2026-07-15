import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { ERA_LABEL, ERA_PLACEHOLDER, ERA_PLACEHOLDER_DEFAULT } from '@/types/era'
import type { EntityBundleBase } from '../types'

// Leaf (per-disc) record within a collection. Renamed from the former
// LibrarySetItemData; single-disc games are collections-of-one.
export interface GameItemData {
  id: number
  software_collection_id: number
  disc_number: number
  media_path: string
  executable_path: string | null
  cover_art_path: string | null
  cover_art_url: string | null
  media_type: string | null
  folder_path: string | null
  detection_reason: string | null
  file_size_bytes: number | null
  created_at?: string | null
  updated_at?: string | null
}

export interface GameItemBundleData extends EntityBundleBase {
  sort_title: string | null
  era: string
  category: string | null
  publisher: string | null
  developer: string | null
  genres: string[]
  year: number | null
  external_game_id: number | null
  metadata_source: string | null
  content_rating: string | null
  launch_commands: string[] | null
  installed: boolean
  requires_install: boolean
  launch_review_flagged: boolean
  // None = inherit the global delete_media_on_removal setting; true/false overrides it.
  delete_media_override: boolean | null
  environment_item_id : number | null
  profile_item_id: number | null
  drive_id: number | null
  launch_disk_id: number | null
  display_disk_id: number | null
  last_launched_at: string | null
  launch_count: number
  // Backend-computed pre-launch gate: "no_profile" | "no_environment" | null.
  // The single source of truth for launch gating (see launchGateFromReason).
  launch_blocked_reason: string | null
  items: GameItemData[]
}

// Game's cover art lives on the leaf item (keyed by display/launch disk id),
// not the bundle itself — this is the CoverArtResolver<GameItemBundleData>.
export function getGameCoverArt(bundle: GameItemBundleData): string | null {
  const effectiveDisplayId = bundle.display_disk_id ?? bundle.launch_disk_id
  const displayDisc = bundle.items.find((d) => d.id === effectiveDisplayId) ?? bundle.items[0]
  return displayDisc?.cover_art_url ?? null
}

// Literal hex tints per era key (lowercase) for chip borders/backgrounds
const ERA_HEX: Record<string, string> = {
  dos: '#d6a64a', win95: '#b6d36b', win98: '#6ea8d6', winxp: '#66b27a',
  ps1: '#a9a0d6', ps2: '#6090d0', xbox: '#6db36d', dreamcast: '#d0a060',
  nes: '#d06060', n64: '#60a0d0', snes: '#d4a0c0',
}

function eraHex(era: string) {
  return ERA_HEX[era] ?? '#6aa9d6'
}

// Full placeholder for the front face when no cover art exists
function ArtPlaceholder({ collection }: { collection: GameItemBundleData }) {
  const style = ERA_PLACEHOLDER[collection.era] ?? ERA_PLACEHOLDER_DEFAULT
  const label = ERA_LABEL[collection.era] ?? (collection.era?.toUpperCase() ?? '—')
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
        {collection.year && <span className="font-mono text-[10px] text-neutral-500">{collection.year}</span>}
      </div>
      <div className="mt-auto">
        <p
          className="font-sans text-[15px] font-semibold leading-snug tracking-tight text-neutral-100"
          style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}
        >
          {collection.title}
        </p>
        {collection.publisher && (
          <p className="mt-1 truncate font-mono text-[10px] tracking-[0.04em] text-neutral-500">
            {collection.publisher}
          </p>
        )}
      </div>
    </div>
  )
}

// Compact era-tinted placeholder for background stack layers
function MiniPlaceholder({ discNumber, era }: { discNumber: number; era: string }) {
  const style = ERA_PLACEHOLDER[era] ?? ERA_PLACEHOLDER_DEFAULT
  return (
    <div
      className="absolute inset-0 flex items-end overflow-hidden"
      style={{ background: style.bg, color: style.color, padding: '7px 9px' }}
    >
      <div aria-hidden className="absolute bottom-0 left-0 top-0 w-[4px]" style={{ background: 'currentColor' }} />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, transparent 0 6px, currentColor 6px 7px),' +
            'repeating-linear-gradient(90deg, transparent 0 6px, currentColor 6px 7px)',
        }}
      />
      <p
        className="relative font-sans text-[10px] font-semibold leading-[1.15] tracking-[-0.005em] text-neutral-100"
        style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}
      >
        Disc {discNumber}
      </p>
    </div>
  )
}

function StackGlyph() {
  return (
    <svg
      width={13} height={13} viewBox="0 0 16 16" fill="none"
      stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round"
      style={{ display: 'block', opacity: 0.9 }}
    >
      <rect x="2.25" y="6" width="7.5" height="7.5" rx="1.5" />
      <path d="M6 6V4.5A1.5 1.5 0 0 1 7.5 3H13A1.5 1.5 0 0 1 14.5 4.5V10A1.5 1.5 0 0 1 13 11.5h-1.5" />
    </svg>
  )
}

// Shared layer base classes — absolute fill, rounded, overflow-hidden, dark bg, shadow + eased transition
const LAYER_BASE =
  'absolute inset-0 overflow-hidden rounded-xl bg-[#1a1f27] shadow-[0_1px_2px_rgb(20_12_6/0.4)] ' +
  'transition-[transform,box-shadow] duration-[220ms] ease-[cubic-bezier(0.16,1,0.3,1)]'

interface CollectionCardProps {
  collection: GameItemBundleData
  onRemove?: (collection: GameItemBundleData) => void
  onSetDisplayDisk?: (collectionId: number, discId: number) => void
}

export function CollectionCard({ collection, onRemove, onSetDisplayDisk }: CollectionCardProps) {
  // Effective display disc — display_disk_id overrides, falls back to launch_disk_id
  const effectiveDisplayId = collection.display_disk_id ?? collection.launch_disk_id
  const displayDisc = collection.items.find((d) => d.id === effectiveDisplayId) ?? collection.items[0]
  const launchDisc = collection.items.find((d) => d.id === collection.launch_disk_id) ?? collection.items[0]
  const launchDiffersFromDisplay = !!displayDisc && !!launchDisc && displayDisc.id !== launchDisc.id

  // Background layers: remaining items sorted by disc_number; b=mid (closer), c=back (farther)
  const bgItems = collection.items
    .filter((d) => d.id !== displayDisc?.id)
    .sort((a, b) => a.disc_number - b.disc_number)
  const layerB = bgItems[0]
  const layerC = bgItems[1]

  const discCount = collection.items.length
  const isMultiDisc = discCount > 1
  const chipHex = eraHex(collection.era)
  const to = collection.slug ? `/software/games/${collection.slug}` : `/software/games/${collection.id}`

  return (
    <div className="group relative flex flex-col gap-2.5">
      <Link
        to={to}
        className="flex flex-col gap-2.5 rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff8a5c] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950"
      >
      {/* Padding-right/top gives space for the peeking background layers */}
      <div style={{ padding: '12px 12px 0 0' }}>
        <div className="relative aspect-video">

          {/* Layer C — back (farthest), z=1 */}
          {layerC && (
            <div className={`${LAYER_BASE} z-[1] translate-x-3 -translate-y-3 group-hover:translate-x-4 group-hover:-translate-y-4`}>
              {layerC.cover_art_url ? (
                <img src={layerC.cover_art_url} alt={`Disc ${layerC.disc_number}`} loading="lazy" className="h-full w-full object-cover" />
              ) : (
                <MiniPlaceholder discNumber={layerC.disc_number} era={collection.era} />
              )}
              <div className="absolute inset-0 bg-[rgb(8_10_13/0.55)]" />
            </div>
          )}

          {/* Layer B — mid, z=2 */}
          {layerB && (
            <div className={`${LAYER_BASE} z-[2] translate-x-1.5 -translate-y-1.5 group-hover:translate-x-2 group-hover:-translate-y-2`}>
              {layerB.cover_art_url ? (
                <img src={layerB.cover_art_url} alt={`Disc ${layerB.disc_number}`} loading="lazy" className="h-full w-full object-cover" />
              ) : (
                <MiniPlaceholder discNumber={layerB.disc_number} era={collection.era} />
              )}
              <div className="absolute inset-0 bg-[rgb(8_10_13/0.34)]" />
            </div>
          )}

          {/* Layer A — front (display disc), z=3 */}
          <div className={`${LAYER_BASE} z-[3] group-hover:-translate-y-0.5 group-hover:shadow-[0_4px_12px_rgb(20_12_6/0.45)]`}>
            {displayDisc?.cover_art_url ? (
              <img src={displayDisc.cover_art_url} alt={collection.title} loading="lazy" className="h-full w-full object-cover" />
            ) : (
              <ArtPlaceholder collection={collection} />
            )}

            {/* Stack count badge — bottom right, only for multi-disc collections */}
            {isMultiDisc && (
              <div className="absolute bottom-2 right-2 z-[4] inline-flex items-center gap-1.5 rounded-[4px] border border-white/[0.16] bg-[rgb(13_16_20/0.80)] px-[7px] py-[4px] font-mono text-[11px] font-bold leading-none tracking-[0.04em] text-[#f3efe9] backdrop-blur-[6px]">
                <StackGlyph />
                {discCount}
              </div>
            )}

            {/* Divergence badge — bottom left, only when display disc ≠ launch disc */}
            {launchDiffersFromDisplay && launchDisc && (
              <div
                className="absolute bottom-2 left-2 z-[4] inline-flex items-center gap-1 rounded-[4px] border bg-black/[0.78] px-[7px] py-[4px] font-mono text-[10px] font-semibold leading-none tracking-[0.04em] backdrop-blur-[6px]"
                style={{ color: '#ff8a5c', borderColor: 'rgb(255 138 92 / 0.40)' }}
                title={`Disc ${launchDisc.disc_number} will launch`}
              >
                ▶ Disc {launchDisc.disc_number}
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

          {/* Disc strip — hover-revealed, z above all layers; click to promote display disc */}
          {isMultiDisc && (
            <div className="absolute bottom-0 left-0 right-0 z-[10] flex gap-1 overflow-x-auto bg-gradient-to-t from-black/80 to-transparent px-2 pb-2 pt-4 opacity-0 transition-opacity duration-[180ms] ease-out group-hover:opacity-100">
              {collection.items
                .slice()
                .sort((a, b) => a.disc_number - b.disc_number)
                .map((disc) => {
                  const isDisplay = disc.id === displayDisc?.id
                  const isLaunch = disc.id === collection.launch_disk_id
                  return (
                    <button
                      key={disc.id}
                      type="button"
                      onClick={() => !isDisplay && onSetDisplayDisk?.(collection.id, disc.id)}
                      disabled={isDisplay}
                      title={isDisplay ? 'Displayed' : isLaunch ? 'Set as display cover (launches this disc)' : 'Set as display cover'}
                      className={`shrink-0 rounded border font-mono text-[9px] px-1.5 py-0.5 transition-colors duration-[120ms] ${
                        isDisplay
                          ? 'cursor-default border-[#ff8a5c]/60 bg-[#ff8a5c]/10 text-[#ff8a5c]/90'
                          : 'cursor-pointer border-neutral-700 bg-black/40 text-neutral-400 hover:border-neutral-500 hover:text-neutral-200'
                      }`}
                    >
                      {isLaunch && !isDisplay ? '▶ ' : ''}{disc.disc_number}
                    </button>
                  )
                })}
            </div>
          )}
        </div>
      </div>

      {/* Title + tag row */}
      <div className="flex min-w-0 flex-col gap-[5px]">
        <span className="min-w-0 truncate font-sans text-sm font-semibold tracking-tight text-neutral-100">
          {collection.title}
        </span>
        <div className="flex gap-[5px] overflow-hidden">
          {collection.era && collection.era !== 'unknown' && (
            <span
              className="inline-flex shrink-0 items-center rounded-[4px] border px-[7px] py-1 font-mono text-[10.5px] font-medium leading-none tracking-[0.08em]"
              style={{ color: chipHex, borderColor: `${chipHex}6a`, background: `${chipHex}1a` }}
            >
              {ERA_LABEL[collection.era] ?? collection.era.toUpperCase()}
            </span>
          )}
          {isMultiDisc && (
            <>
              <span className="inline-flex shrink-0 items-center rounded-[4px] border border-[#6aa9d6]/40 bg-[#6aa9d6]/[0.08] px-[7px] py-1 font-mono text-[10.5px] font-medium leading-none tracking-[0.04em] text-[#b3d6f0]">
                Collection
              </span>
              <span className="inline-flex shrink-0 items-center rounded-[4px] border border-neutral-700 bg-transparent px-[7px] py-1 font-mono text-[10.5px] leading-none tracking-[0.04em] text-[#8a8f99]">
                {discCount} items
              </span>
            </>
          )}
        </div>
      </div>
      </Link>

      {/* Remove — hover-revealed, outside stack area to avoid z-index conflicts */}
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(collection)}
          className="absolute right-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-transparent bg-black/70 text-neutral-400 opacity-0 backdrop-blur-sm transition-opacity duration-[120ms] group-hover:opacity-100 hover:border-red-500/40 hover:text-red-400"
          aria-label={`Remove ${collection.title}`}
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  )
}
