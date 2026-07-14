import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import type { CoverArtResolver, EntityBundleBase } from '../types'

interface EntityCardProps<TBundle extends EntityBundleBase> {
  entity: TBundle
  routeBase: string
  coverArt: CoverArtResolver<TBundle>
  onRemove?: (entity: TBundle) => void
}

// Simple, era/disc-agnostic card for domains without Game's multi-disc stack
// visuals (Media, App). Routes by numeric id, not slug — Media/App bundles
// have no by-slug lookup endpoint on the backend, unlike Game.
export function EntityCard<TBundle extends EntityBundleBase>({
  entity,
  routeBase,
  coverArt,
  onRemove,
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
