import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import type { CoverArtResolver, EntityBundleBase, EntityMultiDiscLeaf } from '../types'

// Per-entity multi-disc data, computed by EntityListPage from
// config.multiDisc for bundles with more than one leaf item. Undefined for
// every domain without a multiDisc config (Media, App today), which renders
// none of the strip markup below at all.
export interface EntityCardMultiDiscProps {
  discs: EntityMultiDiscLeaf[]
  displayDiskId: number | null
  launchDiskId: number | null
  onSetDisplayDisk: (discId: number) => void
}

interface EntityCardProps<TBundle extends EntityBundleBase> {
  entity: TBundle
  routeBase: string
  coverArt: CoverArtResolver<TBundle>
  onRemove?: (entity: TBundle) => void
  multiDisc?: EntityCardMultiDiscProps
}

// Compact, hover-revealed strip of disc buttons, ported (trimmed down) from
// CollectionCard.tsx's disc strip. Click promotes a disc to be the display
// cover; the current display disc is shown disabled, the launch disc (if it
// differs) is marked with a play glyph.
function MultiDiscStrip({ discs, displayDiskId, launchDiskId, onSetDisplayDisk }: EntityCardMultiDiscProps) {
  return (
    <div
      className="absolute bottom-0 left-0 right-0 z-10 flex gap-1 overflow-x-auto bg-gradient-to-t from-black/80 to-transparent px-2 pb-2 pt-4 opacity-0 transition-opacity duration-[180ms] ease-out group-hover:opacity-100"
      onClick={(e) => e.stopPropagation()}
    >
      {discs
        .slice()
        .sort((a, b) => a.disc_number - b.disc_number)
        .map((disc) => {
          const isDisplay = disc.id === displayDiskId
          const isLaunch = disc.id === launchDiskId
          return (
            <button
              key={disc.id}
              type="button"
              onClick={(e) => { e.preventDefault(); if (!isDisplay) onSetDisplayDisk(disc.id) }}
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
  )
}

// Simple, era/disc-agnostic card for domains without Game's multi-disc stack
// visuals (Media, App). Routes by numeric id, not slug, Media/App bundles
// have no by-slug lookup endpoint on the backend, unlike Game. The `multiDisc`
// prop is a slot only, no domain populates it today (see EntityMultiDiscConfig
// in types.ts), so the strip below never renders in current usage.
export function EntityCard<TBundle extends EntityBundleBase>({
  entity,
  routeBase,
  coverArt,
  onRemove,
  multiDisc,
}: EntityCardProps<TBundle>) {
  const to = `${routeBase}/${entity.id}`
  const art = coverArt(entity)

  return (
    <div className="group relative flex flex-col gap-2.5">
      <Link
        to={to}
        className="flex flex-col gap-2.5 rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff8a5c] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950"
      >
        <div className="relative aspect-video overflow-hidden rounded-xl bg-[#1a1f27] shadow-[0_1px_2px_rgb(20_12_6/0.4)]">
          {art ? (
            <img src={art} alt={entity.title} loading="lazy" className="h-full w-full object-cover" />
          ) : (
            <div className="absolute inset-0 flex items-end p-3.5">
              <p
                className="font-sans text-[15px] font-semibold leading-snug tracking-tight text-neutral-100"
                style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden' }}
              >
                {entity.title}
              </p>
            </div>
          )}
          {multiDisc && <MultiDiscStrip {...multiDisc} />}
        </div>
        <span className="min-w-0 truncate font-sans text-sm font-semibold tracking-tight text-neutral-100">
          {entity.title}
        </span>
      </Link>

      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(entity)}
          className="absolute right-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-transparent bg-black/70 text-neutral-400 opacity-0 backdrop-blur-sm transition-opacity duration-[120ms] group-hover:opacity-100 hover:border-red-500/40 hover:text-red-400"
          aria-label={`Remove ${entity.title}`}
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  )
}
