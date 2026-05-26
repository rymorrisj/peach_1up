import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import type { CatalogEntry } from '@/pages/FirstRun/types'
import type { components } from '@shared/types'
type LaunchProfile = components['schemas']['ProfileRead']

const ERA_MAP: Record<string, string[]> = {
  'dosbox-x':   ['DOS', 'WIN31'],
  '86box':       ['WIN95', 'WIN98'],
  'virtualbox':  ['WIN95', 'WIN98', 'WINXP'],
  'duckstation': ['PS1'],
  'pcsx2':       ['PS2'],
  'xemu':        ['XBOX'],
  'flycast':     ['DC'],
  'mesen':       ['NES'],
  'project64':   ['N64'],
  'scummvm':     ['DOS'],
}

const ERA_COLOR: Record<string, string> = {
  DOS:   'var(--era-dos)',
  WIN31: 'var(--era-win31)',
  WIN95: 'var(--era-win95)',
  WIN98: 'var(--era-win98)',
  WINXP: 'var(--era-winxp)',
  PS1:   '#a9a0d6',
  PS2:   '#6090d0',
  XBOX:  '#6db36d',
  DC:    '#d0a060',
  NES:   '#d06060',
  N64:   '#60a0d0',
}

type Tab = 'overview' | 'rom' | 'ext' | 'profiles'

function TabBtn({ id, label, count, active, onClick }: {
  id: Tab; label: string; count?: number; active: boolean; onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '10px 14px',
        border: 0,
        background: 'transparent',
        borderBottom: active ? '2px solid var(--peach-500)' : '2px solid transparent',
        color: active ? 'var(--fg-1)' : 'var(--fg-3)',
        fontFamily: 'var(--font-display)',
        fontWeight: 600,
        fontSize: 13,
        lineHeight: 1,
        cursor: 'pointer',
        marginBottom: -1,
      }}
    >
      {label}
      {count != null && (
        <span style={{ opacity: 0.55, marginLeft: 6, fontFamily: 'var(--font-mono)' }}>{count}</span>
      )}
    </button>
  )
}

function KVTable({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>
        {rows.map(({ label, value }) => (
          <tr key={label}>
            <td style={{ padding: '10px 0', borderBottom: '1px solid var(--border)', fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)', width: 140, verticalAlign: 'top' }}>
              {label}
            </td>
            <td style={{ padding: '10px 0', borderBottom: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
              {value}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function EmulatorDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('overview')

  const { data: catalog = [] } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulators'),
    staleTime: 10_000,
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const entry = catalog.find((e) => e.slug === slug)
  const eras = slug ? (ERA_MAP[slug] ?? []) : []
  const emulatorProfiles = profiles.filter((p) => p.emulator_slug === slug)
  const isReady = entry?.is_installed && entry?.install_path

  if (catalog.length > 0 && !entry) {
    return (
      <div className="p-6" style={{ color: 'var(--fg-3)' }}>
        Emulator not found.
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button
          type="button"
          onClick={() => navigate('/emulators')}
          style={{
            background: 'transparent',
            border: 0,
            color: 'var(--fg-1)',
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
            padding: '6px 10px',
          }}
        >
          ← Emulators
        </button>
        <span style={{ flex: 1 }} />
      </TopBar>

      <div className="p-6">
        {/* Header */}
        <div className="flex items-center gap-3.5 mb-1.5">
          <div
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              width: 56,
              height: 56,
              background: 'var(--surface-2)',
              border: '1px solid var(--border-strong)',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: 22,
              color: 'var(--peach-300)',
            }}
          >
            {entry ? entry.name.slice(0, 2).toUpperCase() : '??'}
          </div>
          <div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, letterSpacing: '-0.02em', margin: 0, color: 'var(--fg-1)' }}>
              {entry?.name ?? slug}
            </h1>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-3)', marginTop: 6 }}>
              {entry?.version}{entry?.install_path && ` · ${entry.install_path}`}
            </div>
          </div>
          <span style={{ flex: 1 }} />
          <div className="flex gap-1.5">
            {eras.map((era) => (
              <span
                key={era}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  fontSize: 11,
                  letterSpacing: '0.08em',
                  padding: '4px 6px',
                  borderRadius: 'var(--r-1)',
                  border: `1px solid ${ERA_COLOR[era] ?? 'var(--border)'}`,
                  color: ERA_COLOR[era] ?? 'var(--fg-3)',
                  display: 'inline-block',
                }}
              >
                {era}
              </span>
            ))}
          </div>
        </div>

        {entry && (
          <p style={{ fontFamily: 'var(--font-display)', fontSize: 14, lineHeight: 1.55, color: 'var(--fg-2)', maxWidth: 760, margin: '14px 0 22px' }}>
            {entry.description}
          </p>
        )}

        {/* Tabs */}
        <div className="flex gap-0" style={{ borderBottom: '1px solid var(--border)', marginBottom: 18 }}>
          <TabBtn id="overview" label="Overview" active={tab === 'overview'} onClick={() => setTab('overview')} />
          <TabBtn id="rom" label="ROM Packs" active={tab === 'rom'} onClick={() => setTab('rom')} />
          <TabBtn id="ext" label="Extensions" active={tab === 'ext'} onClick={() => setTab('ext')} />
          <TabBtn id="profiles" label="Profiles" count={emulatorProfiles.length} active={tab === 'profiles'} onClick={() => setTab('profiles')} />
        </div>

        {/* Overview tab */}
        {tab === 'overview' && entry && (
          <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 12 }}>
                Configuration
              </div>
              <KVTable rows={[
                { label: 'Executable', value: entry.install_path ?? '—' },
                { label: 'Version',    value: entry.version },
                { label: 'Install type', value: entry.install_type },
                { label: 'Eras',       value: eras.join(' · ') || '—' },
                { label: 'Status',     value: isReady ? 'Ready' : 'Not installed' },
              ]} />
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>Sandbox isolation</span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                  padding: '4px 8px', borderRadius: 'var(--r-1)',
                  background: entry.container_enabled ? 'color-mix(in srgb, var(--peach-500) 12%, transparent)' : 'var(--surface-2)',
                  color: entry.container_enabled ? 'var(--peach-400)' : 'var(--fg-3)',
                  border: `1px solid ${entry.container_enabled ? 'var(--peach-500)' : 'var(--border)'}`,
                }}>
                  {entry.container_enabled ? 'AppContainer' : 'Job Object'}
                </span>
              </div>
            </div>
            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 12 }}>
                At a glance
              </div>
              <div className="grid grid-cols-2 gap-3.5">
                {[
                  { value: String(emulatorProfiles.length), label: 'profiles' },
                  { value: eras.length > 0 ? String(eras.length) : '—', label: 'eras' },
                  { value: entry.license ?? '—', label: 'license' },
                  { value: isReady ? '✓' : '✗', label: 'installed' },
                ].map(({ value, label }) => (
                  <div key={label}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 22, lineHeight: 1, color: 'var(--fg-1)' }}>
                      {value}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 4 }}>
                      {label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ROM Packs tab */}
        {tab === 'rom' && (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 13, padding: '16px 18px' }}>
              ROM pack management is available from the Emulators settings. Check your emulator's ROM pack directory for installed packs.
            </div>
          </div>
        )}

        {/* Extensions tab */}
        {tab === 'ext' && (
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
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        padding: '4px 8px',
                        borderRadius: 'var(--r-1)',
                        border: '1px solid var(--border)',
                        color: 'var(--fg-2)',
                        background: 'var(--surface-2)',
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
        )}

        {/* Profiles tab */}
        {tab === 'profiles' && (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            {/* Header row */}
            <div
              className="grid px-[18px] py-2.5"
              style={{
                gridTemplateColumns: '1.7fr 0.7fr 0.8fr 0.5fr',
                fontFamily: 'var(--font-mono)',
                fontWeight: 500,
                fontSize: 11,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'var(--fg-3)',
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
                  onClick={() => navigate(`/profiles/${p.id}`)}
                  className="grid w-full px-[18px] py-3.5 text-left transition-colors duration-[120ms]"
                  style={{
                    gridTemplateColumns: '1.7fr 0.7fr 0.8fr 0.5fr',
                    alignItems: 'center',
                    gap: 8,
                    borderBottom: i < emulatorProfiles.length - 1 ? '1px solid var(--border)' : 'none',
                    background: 'transparent',
                    border: i < emulatorProfiles.length - 1 ? '0' : 'none',
                    borderBottomColor: 'var(--border)',
                    cursor: 'pointer',
                    display: 'grid',
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
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 600,
                        fontSize: 11,
                        letterSpacing: '0.08em',
                        padding: '4px 6px',
                        borderRadius: 'var(--r-1)',
                        border: `1px solid ${ERA_COLOR[p.era.toUpperCase()] ?? 'var(--border)'}`,
                        color: ERA_COLOR[p.era.toUpperCase()] ?? 'var(--fg-3)',
                        display: 'inline-block',
                        textTransform: 'uppercase',
                      }}
                    >
                      {p.era.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
                    {p.slug}
                  </div>
                  <div style={{ textAlign: 'right', color: 'var(--fg-3)' }}>›</div>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
