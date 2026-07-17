import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

interface CloneRomPackButtonProps {
  romPackEntry: CatalogEntry
  isCloning: boolean
  cloneError: string | null
  onClone: () => void
  compact?: boolean
}

export function CloneRomPackButton({ romPackEntry, isCloning, cloneError, onClone, compact = false }: CloneRomPackButtonProps) {
  return (
    <>
      {!romPackEntry.is_installed && romPackEntry.git_available !== false && (
        <button
          type="button"
          onClick={onClone}
          disabled={isCloning}
          style={{
            border: 'none', fontFamily: 'var(--font-display)', fontWeight: 600, cursor: 'pointer',
            fontSize: compact ? 12 : 13,
            padding: compact ? '4px 10px' : '9px 14px',
            borderRadius: compact ? 'var(--r-1)' : 'var(--r-2)',
            background: 'rgb(var(--peach-500))', color: 'rgb(var(--fg-inverse))', opacity: isCloning ? 0.5 : 1,
          }}
        >
          {isCloning ? 'Cloning…' : 'Clone ROM Pack'}
        </button>
      )}
      {!romPackEntry.is_installed && romPackEntry.git_available === false && (
        <span style={{ fontFamily: 'var(--font-display)', fontSize: compact ? 12 : 13, color: 'rgb(var(--warning))' }}>
          git not found on PATH
        </span>
      )}
      {cloneError && (
        <div style={{ marginTop: compact ? 6 : 8, fontSize: '0.75rem', color: 'rgb(var(--error))', fontFamily: 'var(--font-display)' }}>
          {cloneError}
        </div>
      )}
    </>
  )
}
