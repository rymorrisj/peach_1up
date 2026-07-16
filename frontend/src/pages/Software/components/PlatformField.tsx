import { FormField } from '@/ui'
import type { components } from '@shared/types'

type Platform = components['schemas']['EnvironmentItemRead']

const SELECT_CLASS =
  'w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-50'

interface PlatformFieldProps {
  /** Whether this item can launch via an Environment at all (Games: era is
   *  PC, Apps: is_pc). Everything else about the field derives from this. */
  isPcLaunchable: boolean
  /** The item's own era (e.g. "win98") -- an Environment option is only
   *  selectable if its era matches this exactly. Mirrors the backend
   *  authoritative gate (compute_launch_blocked_reason's
   *  "environment_era_mismatch") that closed the incident where a win98 item
   *  silently launched against a win95-era Environment. */
  itemEra: string
  value: string
  onChange: (value: string) => void
  platforms: Platform[]
  /** Shown as the field's hint only while disabled, explaining why there is
   *  no Environment picker for this item. */
  disabledNote: string
}

// DOS/DOSBox-X environments have no OS install step, so they are always
// treated as installed regardless of installed_at -- mirrors
// era_defaults.environment_is_installed on the backend exactly, so the
// frontend and backend gates can't drift apart.
function isEnvironmentInstalled(p: Platform): boolean {
  return p.era === 'dos' ? true : !!p.installed_at
}

function unselectableReason(p: Platform, itemEra: string): string | null {
  if (p.era !== itemEra) return 'different era'
  if (!p.is_present) return 'not present'
  if (!isEnvironmentInstalled(p)) return 'OS not installed yet'
  return null
}

// Shared by EditForm.tsx (Games, gated on era) and AppEditForm.tsx (Apps,
// gated on is_pc) so the enabled/disabled-with-note behavior lives in one
// place instead of being reimplemented per domain. Console items have no
// per-item Environment (the era-to-emulator mapping is fixed), so the field
// stays visible but disabled rather than being hidden, per the "Platform"
// label's existing meaning, only what populates and gates it changes here.
//
// Per-option gating mirrors the same disabled+note pattern used for the
// whole field: an Environment that does not match the item's era, is not
// live-present (compute_environment_presence), or has not had its OS
// installed yet shows as a disabled option with the reason appended, rather
// than being silently omitted or silently selectable -- same "explain why,
// don't hide" philosophy as the field-level disabledNote.
export function PlatformField({ isPcLaunchable, itemEra, value, onChange, platforms, disabledNote }: PlatformFieldProps) {
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
        {isPcLaunchable && platforms.map((p) => {
          const reason = unselectableReason(p, itemEra)
          return (
            <option key={p.id} value={p.id} disabled={reason != null}>
              {reason ? `${p.name} — ${reason}` : p.name}
            </option>
          )
        })}
      </select>
    </FormField>
  )
}
