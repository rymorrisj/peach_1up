import { FormField } from '@/ui'
import { isHealthy } from '@/pages/System/Health'
import type { components } from '@shared/types'

type Platform = components['schemas']['EnvironmentItemRead']

const SELECT_CLASS =
  'w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-50'

interface PlatformFieldProps {
  /** Whether this item can launch via an Environment at all (Games: era is
   *  PC, Apps: is_pc). Everything else about the field derives from this. */
  isPcLaunchable: boolean
  value: string
  onChange: (value: string) => void
  platforms: Platform[]
  /** Shown as the field's hint only while disabled, explaining why there is
   *  no Environment picker for this item. */
  disabledNote: string
}

// Shared by EditForm.tsx (Games, gated on era) and AppEditForm.tsx (Apps,
// gated on is_pc) so the enabled/disabled-with-note behavior lives in one
// place instead of being reimplemented per domain. Console items have no
// per-item Environment (the era-to-emulator mapping is fixed), so the field
// stays visible but disabled rather than being hidden, per the "Platform"
// label's existing meaning, only what populates and gates it changes here.
export function PlatformField({ isPcLaunchable, value, onChange, platforms, disabledNote }: PlatformFieldProps) {
  const healthyPlatforms = platforms.filter(isHealthy)

  return (
    <FormField label="Platform" htmlFor="detail-platform" hint={!isPcLaunchable ? disabledNote : undefined}>
      <select
        id="detail-platform"
        value={value}
        disabled={!isPcLaunchable}
        onChange={(e) => onChange(e.target.value)}
        className={SELECT_CLASS}
      >
        <option value="">No platform selected</option>
        {isPcLaunchable && healthyPlatforms.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </FormField>
  )
}
