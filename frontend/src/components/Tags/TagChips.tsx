import { swatchHex } from './swatches'
import type { components } from '@shared/types'
type TagRead = components['schemas']['TagRead']

interface Props {
  tags: TagRead[]
  onRemove?: (tagId: number) => void
}

export default function TagChips({ tags, onRemove }: Props) {
  if (tags.length === 0) {
    return <span className="text-sm text-neutral-400 dark:text-neutral-500">No tags.</span>
  }
  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => {
        const hex = swatchHex(tag.color)
        return (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full border border-neutral-200 bg-neutral-50 px-2.5 py-0.5 text-xs font-medium text-neutral-700 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
          >
            <span
              className="inline-block h-[6px] w-[6px] shrink-0 rounded-full"
              style={{ background: hex }}
            />
            {tag.name}
            {onRemove && (
              <button
                type="button"
                aria-label={`Remove tag ${tag.name}`}
                onClick={() => onRemove(tag.id)}
                className="ml-0.5 rounded-full text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-100 focus:outline-none"
              >
                ×
              </button>
            )}
          </span>
        )
      })}
    </div>
  )
}
