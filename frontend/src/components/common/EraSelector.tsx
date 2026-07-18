import type { Era } from '@/generated/constants'
import { ERA_LABELS } from '@/generated/constants'

type EraFamily = 'PlayStation' | 'Xbox' | 'Nintendo' | 'PC' | 'Other'

// Console family/generation grouping for the picker's layout. Record<Era, EraFamily>
// is exhaustive over the generated Era union (frontend/src/generated/constants.ts,
// itself generated from config/constants.yaml), so adding a new era backend-side
// without adding it here fails to compile instead of silently leaving it out of
// the picker. This is the fix for EraSelector previously hand-rolling its own
// disconnected era list and missing ps3/xbox360.
const ERA_FAMILY: Record<Era, EraFamily> = {
  ps1: 'PlayStation',
  ps2: 'PlayStation',
  ps3: 'PlayStation',
  xbox: 'Xbox',
  xbox360: 'Xbox',
  nes: 'Nintendo',
  snes: 'Nintendo',
  n64: 'Nintendo',
  dos: 'PC',
  win95: 'PC',
  win98: 'PC',
  winxp: 'PC',
  dreamcast: 'Other',
  unknown: 'Other',
}

const FAMILY_ORDER: EraFamily[] = ['PlayStation', 'Xbox', 'Nintendo', 'PC', 'Other']

interface EraGroup {
  label: EraFamily
  eras: Era[]
}

// Era order within each group follows ERA_LABELS' own key order (i.e. config/
// constants.yaml's declaration order), not an independently maintained list.
const ERA_GROUPS: EraGroup[] = FAMILY_ORDER.map((label) => ({
  label,
  eras: (Object.keys(ERA_LABELS) as Era[]).filter((era) => ERA_FAMILY[era] === label),
}))

interface EraSelectorProps {
  value: Era | null
  onChange: (era: Era) => void
  disabled?: boolean
}

export default function EraSelector({ value, onChange, disabled = false }: EraSelectorProps) {
  return (
    <div className="space-y-5">
      {ERA_GROUPS.map((group) => (
        <div key={group.label}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            {group.label}
          </h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {group.eras.map((era) => {
              const selected = value === era
              return (
                <button
                  key={era}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(era)}
                  aria-pressed={selected}
                  className={`rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors ${
                    selected
                      ? 'border-accent bg-accent/10 text-accent dark:bg-accent/20'
                      : 'border-neutral-200 text-neutral-700 hover:border-neutral-400 hover:bg-surface-2 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-neutral-500'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  {ERA_LABELS[era]}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
