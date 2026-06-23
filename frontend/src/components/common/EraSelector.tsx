export type EraValue =
  | 'dos'
  | 'win31'
  | 'win95'
  | 'win98'
  | 'winxp'
  | 'ps1'
  | 'ps2'
  | 'xbox'
  | 'nes'
  | 'snes'
  | 'n64'
  | 'dreamcast'

interface Era {
  value: EraValue
  label: string
}

interface EraGroup {
  label: string
  eras: Era[]
}

const ERA_GROUPS: EraGroup[] = [
  {
    label: 'PC',
    eras: [
      { value: 'dos', label: 'DOS' },
      { value: 'win31', label: 'Windows 3.1' },
      { value: 'win95', label: 'Windows 95' },
      { value: 'win98', label: 'Windows 98' },
      { value: 'winxp', label: 'Windows XP' },
    ],
  },
  {
    label: 'Console',
    eras: [
      { value: 'ps1', label: 'PlayStation 1' },
      { value: 'ps2', label: 'PlayStation 2' },
      { value: 'xbox', label: 'Original Xbox' },
      { value: 'nes', label: 'NES' },
      { value: 'snes', label: 'Super Nintendo' },
      { value: 'n64', label: 'Nintendo 64' },
      { value: 'dreamcast', label: 'Dreamcast' },
    ],
  },
]

interface EraSelectorProps {
  value: EraValue | null
  onChange: (era: EraValue) => void
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
              const selected = value === era.value
              return (
                <button
                  key={era.value}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(era.value)}
                  aria-pressed={selected}
                  className={`rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors ${
                    selected
                      ? 'border-[#ff8a5c] bg-[#ff8a5c]/10 text-[#ff8a5c] dark:bg-[#ff8a5c]/20'
                      : 'border-neutral-200 text-neutral-700 hover:border-neutral-400 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-neutral-500 dark:hover:bg-surface-800'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  {era.label}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
