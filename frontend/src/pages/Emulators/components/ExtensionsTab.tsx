import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

interface ExtensionsTabProps {
  entry: CatalogEntry | undefined
}

export function ExtensionsTab({ entry }: ExtensionsTabProps) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      {entry?.supported_formats && entry.supported_formats.length > 0 ? (
        <div>
          <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
            Supported formats
          </div>
          <div style={{ padding: '14px 18px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {entry.supported_formats.map((fmt) => (
              <span
                key={fmt}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 8px',
                  borderRadius: 'var(--r-1)', border: '1px solid var(--border)',
                  color: 'var(--fg-2)', background: 'var(--surface-2)',
                }}
              >
                {fmt}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 13, padding: '16px 18px' }}>
          No extension information available.
        </div>
      )}
    </div>
  )
}
