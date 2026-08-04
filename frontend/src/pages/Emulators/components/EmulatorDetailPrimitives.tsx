export type Tab = 'overview' | 'rom' | 'ext' | 'limits';

export function TabBtn({
  id: _id,
  label,
  count,
  active,
  onClick,
}: {
  id: Tab;
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '10px 14px',
        border: 0,
        background: 'transparent',
        borderBottom: active ? '2px solid rgb(var(--peach-500))' : '2px solid transparent',
        color: active ? 'rgb(var(--fg-1))' : 'rgb(var(--fg-3))',
        fontFamily: 'var(--font-display)',
        fontWeight: 600,
        fontSize: '0.8125rem',
        lineHeight: 1,
        cursor: 'pointer',
        marginBottom: -1,
      }}
    >
      {label}
      {count != null && (
        <span style={{ opacity: 0.55, marginLeft: 6, fontFamily: 'var(--font-mono)' }}>
          {count}
        </span>
      )}
    </button>
  );
}

export function KVTable({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>
        {rows.map(({ label, value }) => (
          <tr key={label}>
            <td
              style={{
                padding: '10px 0',
                borderBottom: '1px solid rgb(var(--border))',
                fontFamily: 'var(--font-display)',
                fontSize: '0.8125rem',
                color: 'rgb(var(--fg-3))',
                width: 140,
                verticalAlign: 'top',
              }}
            >
              {label}
            </td>
            <td
              style={{
                padding: '10px 0',
                borderBottom: '1px solid rgb(var(--border))',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem',
                color: 'rgb(var(--fg-2))',
              }}
            >
              {value}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function StatusDot({ ok }: { ok: boolean | null | undefined }) {
  return (
    <span style={{ color: ok ? 'rgb(var(--success))' : 'rgb(var(--warning))' }}>
      {ok ? '✓' : '✗'}
    </span>
  );
}

export function GuidanceNote({ text, url }: { text?: string | null; url?: string | null }) {
  if (!text) return null;
  return (
    <div
      style={{
        fontFamily: 'var(--font-display)',
        fontSize: '0.8125rem',
        color: 'rgb(var(--fg-3))',
        lineHeight: 1.5,
      }}
    >
      {text}{' '}
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          style={{ color: 'rgb(var(--peach-400))', textDecoration: 'underline' }}
        >
          Download
        </a>
      )}
    </div>
  );
}

export function SandboxToggle({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 0',
        borderBottom: '1px solid rgb(var(--border))',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: '0.8125rem',
          color: 'rgb(var(--fg-3))',
        }}
      >
        {label}
      </span>
      <button
        type="button"
        onClick={() => !disabled && onChange(!value)}
        style={{
          width: 36,
          height: 20,
          borderRadius: 10,
          border: 'none',
          cursor: disabled ? 'default' : 'pointer',
          background: value ? 'rgb(var(--peach-500))' : 'var(--surface-3, rgb(var(--surface-2)))',
          position: 'relative',
          flexShrink: 0,
          opacity: disabled ? 0.5 : 1,
          transition: 'background 150ms',
        }}
      >
        <span
          style={{
            position: 'absolute',
            top: 2,
            left: value ? 18 : 2,
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: 'rgb(var(--fg-inverse))',
            transition: 'left 150ms',
            display: 'block',
          }}
        />
      </button>
    </div>
  );
}
