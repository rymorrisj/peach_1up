import { Button } from '@/ui'
import type { LaunchProfile } from '@/types/profiles'

interface ProfileListProps {
  profiles: LaunchProfile[]
  eraLabel: (era: string) => string
  formatDate: (iso: string) => string
  onSelect: (profile: LaunchProfile) => void
  onEdit: (profile: LaunchProfile) => void
  onDelete: (profile: LaunchProfile) => void
}

export function ProfileList({ profiles, eraLabel, formatDate, onSelect, onEdit, onDelete }: ProfileListProps) {
  return (
    <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
      {profiles.map((profile) => (
        <li key={profile.id} className="py-4">
          <div className="flex items-center justify-between gap-4">
            <button
              type="button"
              onClick={() => onSelect(profile)}
              className="min-w-0 flex-1 text-left"
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {profile.name}
                </span>
                {profile.is_bundled && (
                  <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-500 dark:bg-surface-700 dark:text-neutral-400">
                    default
                  </span>
                )}
                {profile.enable_networking && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                    networking on
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-neutral-400 dark:text-neutral-500">
                {eraLabel(profile.era)} · {profile.emulator_slug}
                {' · '}Created {formatDate(profile.created_at)}
              </p>
            </button>
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => onEdit(profile)}>
                Edit
              </Button>
              {!profile.is_bundled && (
                <Button variant="destructive" size="sm" onClick={() => onDelete(profile)}>
                  Delete
                </Button>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}
