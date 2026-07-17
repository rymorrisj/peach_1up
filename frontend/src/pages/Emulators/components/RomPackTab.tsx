import { GuidanceNote, StatusDot } from './EmulatorDetailPrimitives'
import { CloneRomPackButton } from './CloneRomPackButton'
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
    <div className="rounded-xl overflow-hidden" style={{ background: 'rgb(var(--surface-1))', border: '1px solid rgb(var(--border))' }}>
      {romPackEntry ? (
        <div style={{ padding: '16px 18px' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.875rem', color: 'rgb(var(--fg-1))', marginBottom: 12 }}>
            {romPackEntry.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-display)', fontSize: '0.8125rem', color: 'rgb(var(--fg-3))' }}>
              <StatusDot ok={romPackEntry.is_installed} />
              {romPackEntry.is_installed ? 'ROM pack present' : 'ROM pack missing'}
            </div>
            <CloneRomPackButton
              romPackEntry={romPackEntry}
              isCloning={isCloning}
              cloneError={null}
              onClone={onCloneRomPack}
            />
          </div>
          {!romPackEntry.is_installed && (
            <GuidanceNote text={romPackEntry.guidance_text} url={romPackEntry.guidance_url} />
          )}
          {cloneError && (
            <div style={{ marginTop: 8, fontSize: '0.75rem', color: 'rgb(var(--error))', fontFamily: 'var(--font-display)' }}>
              {cloneError}
            </div>
          )}
          {romPackEntry.is_installed && (
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '0.8125rem', color: 'rgb(var(--success))', marginTop: 4 }}>
              ROM pack installed and ready.
            </div>
          )}
        </div>
      ) : (
        <div style={{ color: 'rgb(var(--fg-3))', fontFamily: 'var(--font-display)', fontSize: '0.8125rem', padding: '16px 18px' }}>
          No ROM packs required for this emulator.
        </div>
      )}
    </div>
  )
}
