import { ERA_COLOR } from '@/types/era'
import type { components } from '@shared/types'
type LaunchProfile = components['schemas']['ProfileRead']

interface ProfilesTabContentProps {
  emulatorProfiles: LaunchProfile[]
  onNavigateToProfile: (slug: string) => void
}

export function ProfilesTabContent({ emulatorProfiles, onNavigateToProfile }: ProfilesTabContentProps) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <div
        className="grid px-[18px] py-2.5"
        style={{
          gridTemplateColumns: '1.7fr 0.7fr 0.8fr 0.5fr',
          fontFamily: 'var(--font-mono)', fontWeight: 500, fontSize: 11,
          letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <span>Profile</span><span>Era</span><span>Slug</span><span></span>
      </div>
      {emulatorProfiles.length === 0 ? (
        <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 13, padding: '16px 18px' }}>
          No profiles assigned to this emulator.
        </div>
      ) : (
        emulatorProfiles.map((p, i) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onNavigateToProfile(p.slug)}
            className="grid w-full px-[18px] py-3.5 text-left transition-colors duration-[120ms]"
            style={{
              gridTemplateColumns: '1.7fr 0.7fr 0.8fr 0.5fr', alignItems: 'center', gap: 8,
              borderBottom: i < emulatorProfiles.length - 1 ? '1px solid var(--border)' : 'none',
              background: 'transparent',
              border: i < emulatorProfiles.length - 1 ? '0' : 'none',
              borderBottomColor: 'var(--border)', cursor: 'pointer', display: 'grid',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
          >
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
              {p.name}
            </div>
            <div>
              <span
                style={{
                  fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11,
                  letterSpacing: '0.08em', padding: '4px 6px', borderRadius: 'var(--r-1)',
                  border: `1px solid ${ERA_COLOR[p.era.toUpperCase()] ?? 'var(--border)'}`,
                  color: ERA_COLOR[p.era.toUpperCase()] ?? 'var(--fg-3)',
                  display: 'inline-block', textTransform: 'uppercase',
                }}
              >
                {p.era.toUpperCase()}
              </span>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{p.slug}</div>
            <div style={{ textAlign: 'right', color: 'var(--fg-3)' }}>›</div>
          </button>
        ))
      )}
    </div>
  )
}
