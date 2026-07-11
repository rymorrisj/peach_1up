import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import EmptyState from '@/components/common/EmptyState'
import { StatusDot, GuidanceNote } from './components/EmulatorDetailPrimitives'
import { BiosPlaceAction } from './components/BiosPlaceAction'
import type { components } from '@shared/types'
type BiosRequirement = components['schemas']['BiosRequirement']

// GET /api/v1/bios returns a bare list[BiosRequirement], not a Page[T]
// envelope (dev_docs/v2/08_emulator_profiles_navigation.md, Task 3) — mounted
// without pagination controls; flagged for the batched backend pass.
export default function Bios() {
  const { data: bios = [], isLoading } = useQuery<BiosRequirement[]>({
    queryKey: ['bios-requirements'],
    queryFn: () => apiFetch<BiosRequirement[]>('/api/v1/bios'),
  })

  return (
    <div className="p-6">
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--fg-3)' }}>
          <LoadingSpinner label="Loading BIOS requirements…" />
          <span aria-hidden="true">Loading BIOS requirements…</span>
        </div>
      ) : bios.length === 0 ? (
        <EmptyState heading="No BIOS requirements" subtext="No emulators in the catalog require a BIOS asset." />
      ) : (
        <div className="rounded-xl" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          {bios.map((b, i) => (
            <div
              key={b.slug}
              style={{ padding: '14px 18px', borderBottom: i < bios.length - 1 ? '1px solid var(--border)' : 'none' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
                  {b.name}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
                  border: '1px solid var(--border)', borderRadius: 'var(--r-1)', padding: '2px 6px',
                }}>
                  {b.required ? 'required' : 'optional'}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase',
                  color: 'var(--fg-3)',
                }}>
                  {b.platform}
                </span>
                <StatusDot ok={b.is_present} />
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginBottom: 6 }}>
                {b.bios_path}/
              </div>
              {b.is_present ? (
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: '#4ade80' }}>
                  Files detected
                </div>
              ) : (
                <GuidanceNote text={b.guidance_text} url={b.guidance_url} />
              )}
              <BiosPlaceAction bios={b} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
