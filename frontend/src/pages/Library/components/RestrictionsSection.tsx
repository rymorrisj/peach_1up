import { Button } from '@/ui'
import type { components } from '@shared/types'

type User = components['schemas']['UserRead']

interface RestrictionsSectionProps {
  users: User[]
  restrictedIds: Set<number>
  restrictionsDirty: boolean
  toggleRestriction: (userId: number) => void
  onSave: () => void
  saving: boolean
  error: string | null
}

export function RestrictionsSection({
  users,
  restrictedIds,
  restrictionsDirty,
  toggleRestriction,
  onSave,
  saving,
  error,
}: RestrictionsSectionProps) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Restrictions
      </h2>
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Checked users cannot see this item in their library.
      </p>

      {users.length === 0 ? (
        <p className="text-sm text-neutral-400 dark:text-neutral-500">No sub-accounts.</p>
      ) : (
        <ul className="space-y-2">
          {users.map((user) => (
            <li key={user.id}>
              <label className="flex cursor-pointer items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300">
                <input
                  type="checkbox"
                  checked={restrictedIds.has(user.id)}
                  onChange={() => toggleRestriction(user.id)}
                  className="h-4 w-4 rounded border-neutral-300 text-[#ff8a5c] focus:ring-[#ff8a5c] dark:border-neutral-600"
                />
                {user.name}
              </label>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-3">
        <Button
          variant="secondary"
          onClick={onSave}
          loading={saving}
          disabled={!restrictionsDirty || users.length === 0}
        >
          Save Restrictions
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </section>
  )
}
