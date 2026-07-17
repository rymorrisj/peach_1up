interface HelpBarProps {
  hints?: Array<[string, string]>
}

const DEFAULT_HINTS: Array<[string, string]> = [
  ['/', 'Search'],
  ['Esc', 'Back'],
  ['?', 'Help'],
]

export default function HelpBar({ hints = DEFAULT_HINTS }: HelpBarProps) {
  return (
    <div
      className="flex h-9 shrink-0 items-center gap-2.5 border-t px-4"
      style={{
        borderColor: 'rgb(var(--border))',
        background: 'rgb(var(--surface-0))',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.75rem',
        color: 'rgb(var(--fg-3))',
      }}
    >
      {hints.map(([key, action], i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span style={{ color: 'rgb(var(--fg-3))', opacity: 0.5 }}>•</span>}
          <kbd
            className="inline-block rounded px-[5px] py-[3px]"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.6875rem',
              fontWeight: 500,
              border: '1px solid rgb(var(--border))',
              background: 'rgb(var(--surface-1))',
              color: 'rgb(var(--fg-2))',
              marginRight: 4,
            }}
          >
            {key}
          </kbd>
          {action}
        </span>
      ))}
    </div>
  )
}
