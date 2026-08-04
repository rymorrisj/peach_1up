import { Button, Checkbox } from '@/ui';
import type { components } from '@shared/types';

type User = components['schemas']['UserItemRead'];

interface RestrictionsSectionProps {
  users: User[];
  restrictedIds: Set<number>;
  restrictionsDirty: boolean;
  toggleRestriction: (userId: number) => void;
  onSave: () => void;
  saving: boolean;
  error: string | null;
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
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Checked users cannot see this item in their library.
      </p>

      {users.length === 0 ? (
        <p className="text-sm text-neutral-400 dark:text-neutral-500">No sub-accounts.</p>
      ) : (
        <ul className="space-y-2">
          {users.map((user) => (
            <li key={user.id}>
              <Checkbox
                checked={restrictedIds.has(user.id)}
                onCheckedChange={() => toggleRestriction(user.id)}
                label={user.name}
              />
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
  );
}
