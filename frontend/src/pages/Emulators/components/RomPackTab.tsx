import { GuidanceNote, StatusDot } from './EmulatorDetailPrimitives'
import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

interface RomPackTabProps {
  romPackEntry: CatalogEntry | undefined
  isCloning: boolean
  cloneError: string | null
  onCloneRomPack: () => void
}

export function RomPackTab({ romPackEntry, isCloning, cloneError, onCloneRomPack }: RomPackTabProps) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      {romPackEntry ? (
        <div style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)', marginBottom: 12 }}>
            {romPackEntry.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
              <StatusDot ok={romPackEntry.is_installed} />
              {romPackEntry.is_installed ? 'ROM pack present' : 'ROM pack missing'}
            </div>
            {!romPackEntry.is_installed && romPackEntry.git_available !== false && (
              <button
                type="button"
                onClick={onCloneRomPack}
                disabled={isCloning}
                style={{
                  border: 'none', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                  padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer',
                  background: 'var(--peach-500)', color: '#fff', opacity: isCloning ? 0.5 : 1,
                }}
              >
                {isCloning ? 'Cloning…' : 'Clone ROM Pack'}
              </button>
            )}
            {!romPackEntry.is_installed && romPackEntry.git_available === false && (
              <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: '#fbbf24' }}>
                git not found on PATH
              </span>
            )}
          </div>
          {!romPackEntry.is_installed && (
            <GuidanceNote text={romPackEntry.guidance_text} url={romPackEntry.guidance_url} />
          )}
          {cloneError && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--error)', fontFamily: 'var(--font-display)' }}>
              {cloneError}
            </div>
          )}
          {romPackEntry.is_installed && (
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: '#4ade80', marginTop: 4 }}>
              ROM pack installed and ready.
            </div>
          )}
        </div>
      ) : (
        <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 13, padding: '16px 18px' }}>
          No ROM packs required for this emulator.
        </div>
      )}
    </div>
  )
}
