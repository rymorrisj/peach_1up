import { TagChips, TagCombobox } from '@/components/Tags'
import type { components } from '@shared/types'

type TagRead = components['schemas']['TagRead']

interface TagsSectionProps {
  entity: { id: number; tags: TagRead[] }
  isAdminOrOwner: boolean
  onRemove: (tagId: number) => void
  onAssign: (tagId: number) => void
  error: string | null
}

export function TagsSection({ entity, isAdminOrOwner, onRemove, onAssign, error }: TagsSectionProps) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Tags
      </h2>

      <TagChips
        tags={entity.tags ?? []}
        onRemove={isAdminOrOwner ? onRemove : undefined}
      />

      {isAdminOrOwner && (
        <TagCombobox
          assignedTagIds={(entity.tags ?? []).map((t) => t.id)}
          onAssign={onAssign}
        />
      )}

      {error && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </section>
  )
}
