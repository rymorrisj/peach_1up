import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import type { components } from '@shared/types'

type Platform = components['schemas']['PlatformRead']

const ERA_COLOR: Record<string, string> = {
  dos:   'var(--era-dos)',
  win31: 'var(--era-win31)',
  win95: 'var(--era-win95)',
  win98: 'var(--era-win98)',
  winxp: 'var(--era-winxp)',
}

const ERA_LABEL: Record<string, string> = {
  dos:   'DOS',
  win31: 'WIN31',
  win95: 'WIN95',
  win98: 'WIN98',
  winxp: 'WINXP',
}

function formatBytes(n: number) {
  if (n >= 1_073_741_824) return `${(n / 1_073_741_824).toFixed(1)} GB`
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(0)} MB`
  return `${n} B`
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function isHealthy(p: Platform) {
  return p.status === 'ok' || p.status === 'healthy' || p.status === 'unknown'
}

function StatusDot({ healthy }: { healthy: boolean }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{
        width: 8,
        height: 8,
        background: healthy ? 'var(--success)' : 'var(--error)',
        boxShadow: healthy
          ? '0 0 12px rgb(110 208 154 / 0.5)'
          : '0 0 12px rgb(255 106 85 / 0.5)',
      }}
    />
  )
}

function EraChip({ era }: { era: string }) {
  const color = ERA_COLOR[era] ?? 'var(--fg-3)'
  const label = ERA_LABEL[era] ?? era.toUpperCase()
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        fontSize: 11,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        padding: '4px 6px',
        borderRadius: 'var(--r-1)',
        border: `1px solid ${color}`,
        color,
        display: 'inline-block',
      }}
    >
      {label}
    </span>
  )
}

export default function PlatformHealth() {
  const queryClient = useQueryClient()

  const { data: platforms = [], isLoading } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const userPlatforms = platforms.filter((p) => !p.is_system)
  const healthy = userPlatforms.filter(isHealthy)
  const degraded = userPlatforms.filter((p) => !isHealthy(p))

  async function handleHealthCheckAll() {
    try {
      await apiFetch('/api/v1/platforms/health-all', { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
    } catch {
      // individual statuses updated via query invalidation
    }
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Platform Health">
        <button
          type="button"
          onClick={handleHealthCheckAll}
          className="ml-auto rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-[120ms]"
          style={{
            fontFamily: 'var(--font-display)',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            color: 'var(--fg-1)',
            cursor: 'pointer',
          }}
        >
          Health Check All
        </button>
      </TopBar>

      <div className="p-6">
        {/* Status section */}
        <div className="mb-3 flex items-baseline gap-2.5">
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, letterSpacing: '-0.01em', margin: 0, color: 'var(--fg-1)' }}>
            Status
          </h2>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-3)' }}>
            {healthy.length} healthy · {degraded.length} degraded
          </span>
          <div style={{ flex: 1 }} />
        </div>

        {degraded.length > 0 && (
          <div
            className="mb-4 flex gap-2.5 rounded-md px-3 py-2.5"
            style={{
              borderLeft: '3px solid var(--error)',
              background: 'rgb(255 106 85 / 0.08)',
            }}
          >
            <span style={{ fontWeight: 600, color: 'var(--error)' }}>✗</span>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, lineHeight: 1.4, color: 'var(--fg-2)' }}>
              <strong>{degraded.length} platform{degraded.length > 1 ? 's need' : ' needs'} attention.</strong>{' '}
              Check your environment configuration or re-register.
            </span>
          </div>
        )}

        {isLoading ? (
          <div
            className="rounded-xl p-6 text-sm"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)', color: 'var(--fg-3)' }}
          >
            Loading…
          </div>
        ) : userPlatforms.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center text-sm"
            style={{
              border: '1px dashed var(--border-strong)',
              color: 'var(--fg-3)',
              backgroundImage:
                'repeating-linear-gradient(0deg, transparent 0 11px, rgb(255 138 92 / 0.04) 11px 12px), repeating-linear-gradient(90deg, transparent 0 11px, rgb(255 138 92 / 0.04) 11px 12px)',
            }}
          >
            No environments registered. Add environments to track platform health.
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            {userPlatforms.map((p, i) => {
              const ok = isHealthy(p)
              return (
                <div
                  key={p.id}
                  className="flex items-center gap-3.5 px-[18px] py-4"
                  style={{ borderBottom: i < userPlatforms.length - 1 ? '1px solid var(--border)' : 'none' }}
                >
                  <StatusDot healthy={ok} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2.5 mb-0.5">
                      <EraChip era={p.era} />
                      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
                        {p.name}
                      </span>
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.4, color: 'var(--fg-3)' }}>
                      Backend: {p.emulator_slug}
                      {p.working_image_path && ` · Working image: ${p.working_image_path}`}
                      {' · '}Last check: {formatDate(p.last_health_check)}
                    </div>
                    {!ok && p.status && (
                      <div className="mt-1.5 flex items-center gap-1.5" style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--warning)' }}>
                        <span>⚠</span>
                        <span>{p.status}</span>
                      </div>
                    )}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500, color: ok ? 'var(--success)' : 'var(--error)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <StatusDot healthy={ok} />
                    {ok ? 'Ready' : 'Degraded'}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Storage section */}
        <div className="mb-3 mt-7 flex items-baseline gap-2.5">
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, letterSpacing: '-0.01em', margin: 0, color: 'var(--fg-1)' }}>
            Storage
          </h2>
        </div>

        <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <div className="grid grid-cols-4 gap-[18px]">
            {[
              { label: 'working images', color: 'var(--peach-500)', pct: '33%' },
              { label: 'base images',   color: 'var(--peach-700)', pct: '50%' },
              { label: 'snapshots',     color: 'var(--era-win98)', pct: '14%' },
              { label: 'profiles + conf', color: 'var(--era-win95)', pct: '3%' },
            ].map(({ label, color }) => (
              <div key={label}>
                <div className="flex items-baseline gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-full shrink-0" style={{ background: color }} />
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 6 }}>
                  {label}
                </div>
              </div>
            ))}
          </div>

          {/* Stacked bar */}
          <div className="mt-4 flex overflow-hidden rounded" style={{ height: 8, background: 'var(--surface-2)' }}>
            <span style={{ width: '33%', background: 'var(--peach-500)' }} />
            <span style={{ width: '50%', background: 'var(--peach-700)' }} />
            <span style={{ width: '14%', background: 'var(--era-win98)' }} />
            <span style={{ width: '3%', background: 'var(--era-win95)' }} />
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)', marginTop: 8 }}>
            Storage breakdown — working images · base images · snapshots · profiles + config
          </div>
        </div>
      </div>
    </div>
  )
}
