import type { components } from '@shared/types';
type CatalogEntry = components['schemas']['CatalogEntryResponse'];

interface ExtensionsTabProps {
  entry: CatalogEntry | undefined;
}

export function ExtensionsTab({ entry }: ExtensionsTabProps) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'rgb(var(--surface-1))', border: '1px solid rgb(var(--border))' }}
    >
      {entry?.supported_formats && entry.supported_formats.length > 0 ? (
        <div>
          <div
            style={{
              padding: '12px 18px',
              borderBottom: '1px solid rgb(var(--border))',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              color: 'rgb(var(--fg-3))',
            }}
          >
            Supported formats
          </div>
          <div style={{ padding: '14px 18px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {entry.supported_formats.map((fmt) => (
              <span
                key={fmt}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6875rem',
                  padding: '4px 8px',
                  borderRadius: 'var(--r-1)',
                  border: '1px solid rgb(var(--border))',
                  color: 'rgb(var(--fg-2))',
                  background: 'rgb(var(--surface-2))',
                }}
              >
                {fmt}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div
          style={{
            color: 'rgb(var(--fg-3))',
            fontFamily: 'var(--font-display)',
            fontSize: '0.8125rem',
            padding: '16px 18px',
          }}
        >
          No extension information available.
        </div>
      )}
    </div>
  );
}
