import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

interface LimitationsTabProps {
  entry: CatalogEntry
}

export function LimitationsTab({ entry }: LimitationsTabProps) {
  return (
    <div className="flex flex-col gap-3">
      {(entry.known_limitations ?? []).map((lim, i) => {
        const { title: limTitle, severity: limSeverity, description: limDescription } = lim as { title: string; severity: string; description: string }
        const severityStyle: React.CSSProperties =
          limSeverity === 'warning'
            ? { background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)', color: '#fbbf24' }
            : limSeverity === 'critical'
            ? { background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.35)', color: '#ef4444' }
            : { background: 'var(--surface-1)', border: '1px solid var(--border)', color: 'var(--fg-3)' }
        return (
          <div key={i} className="rounded-xl p-[18px]" style={{ background: severityStyle.background, border: severityStyle.border }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
                {limTitle}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
                letterSpacing: '0.08em', textTransform: 'uppercase',
                padding: '2px 6px', borderRadius: 'var(--r-1)',
                border: `1px solid ${severityStyle.color}`,
                color: severityStyle.color,
              }}>
                {limSeverity}
              </span>
            </div>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, lineHeight: 1.55, color: 'var(--fg-2)', margin: 0 }}>
              {limDescription}
            </p>
          </div>
        )
      })}
    </div>
  )
}
