import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import { EMULATOR_ERA_MAP, ERA_COLOR } from '@/types/era'
import type { BiosRequirement, EmulatorStatusData } from '@/pages/FirstRun/types'
import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']
type LaunchProfile = components['schemas']['ProfileRead']


const EMULATOR_BIOS_PLATFORM: Record<string, string> = {
  'duckstation': 'ps1',
  'pcsx2':       'ps2',
  'xemu':        'xbox',
  'flycast':     'dreamcast',
}

type Tab = 'overview' | 'rom' | 'ext' | 'profiles' | 'limits'

function TabBtn({ id: _id, label, count, active, onClick }: {
  id: Tab; label: string; count?: number; active: boolean; onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '10px 14px', border: 0, background: 'transparent',
        borderBottom: active ? '2px solid var(--peach-500)' : '2px solid transparent',
        color: active ? 'var(--fg-1)' : 'var(--fg-3)',
        fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13, lineHeight: 1,
        cursor: 'pointer', marginBottom: -1,
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

function StatusDot({ ok }: { ok: boolean | null | undefined }) {
  return (
    <span style={{ color: ok ? '#4ade80' : '#fbbf24' }}>{ok ? '✓' : '✗'}</span>
  )
}

function GuidanceNote({ text, url }: { text?: string | null; url?: string | null }) {
  if (!text) return null
  return (
    <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)', lineHeight: 1.5 }}>
      {text}{' '}
      {url && (
        <a href={url} target="_blank" rel="noreferrer" style={{ color: 'var(--peach-400)', textDecoration: 'underline' }}>
          Download
        </a>
      )}
    </div>
  )
}

function SandboxToggle({ label, value, disabled, onChange }: {
  label: string; value: boolean; disabled?: boolean; onChange: (v: boolean) => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>{label}</span>
      <button
        type="button"
        onClick={() => !disabled && onChange(!value)}
        style={{
          width: 36, height: 20, borderRadius: 10, border: 'none', cursor: disabled ? 'default' : 'pointer',
          background: value ? 'var(--peach-500)' : 'var(--surface-3, var(--surface-2))',
          position: 'relative', flexShrink: 0, opacity: disabled ? 0.5 : 1,
          transition: 'background 150ms',
        }}
      >
        <span style={{
          position: 'absolute', top: 2, left: value ? 18 : 2, width: 16, height: 16,
          borderRadius: '50%', background: '#fff', transition: 'left 150ms', display: 'block',
        }} />
      </button>
    </div>
  )
}

export default function EmulatorDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [sandboxSaving, setSandboxSaving] = useState(false)
  const [isInstalling, setIsInstalling] = useState(false)
  const [installError, setInstallError] = useState<string | null>(null)
  const [isCloning, setIsCloning] = useState(false)
  const [cloneError, setCloneError] = useState<string | null>(null)

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
  const romPackSlug = entry?.rom_pack_slug ?? undefined
  const emulatorBiosPlatform = slug ? EMULATOR_BIOS_PLATFORM[slug] : undefined

  const { data: allBios = [] } = useQuery<BiosRequirement[]>({
    queryKey: ['bios-requirements'],
    queryFn: () => apiFetch<BiosRequirement[]>('/api/v1/bios'),
    enabled: !!emulatorBiosPlatform,
  })

  const { data: installStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulators/${slug}/status`),
    refetchInterval: isInstalling ? 3000 : false,
    enabled: isInstalling && !!slug,
  })

  const { data: cloneStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', romPackSlug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulators/${romPackSlug}/status`),
    refetchInterval: isCloning ? 4000 : false,
    enabled: isCloning && !!romPackSlug,
  })

  const romPackEntry = romPackSlug ? catalog.find((e) => e.slug === romPackSlug) : undefined
  const emulatorBios = allBios.filter((b) => b.platform === emulatorBiosPlatform)
  const eras = slug ? (EMULATOR_ERA_MAP[slug] ?? []) : []
  const emulatorProfiles = profiles.filter((p) => p.emulator_slug === slug)
  const isReady = entry?.is_installed && entry?.install_path

  useEffect(() => {
    if (!installStatus) return
    if (installStatus.binary_detected) {
      setIsInstalling(false)
      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
    }
    if (installStatus.status === 'error') {
      setIsInstalling(false)
      setInstallError(installStatus.error ?? 'Install failed.')
    }
  }, [installStatus])

  useEffect(() => {
    if (!cloneStatus) return
    if (cloneStatus.status === 'complete') {
      setIsCloning(false)
      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
    }
    if (cloneStatus.status === 'error') {
      setIsCloning(false)
      setCloneError(cloneStatus.error ?? 'Clone failed.')
    }
  }, [cloneStatus])

  async function handleSandboxToggle(
    field: 'container_enabled' | 'skip_cpu_limit' | 'skip_memory_limit',
    value: boolean,
  ) {
    if (!slug || sandboxSaving) return
    setSandboxSaving(true)
    try {
      await apiFetch(`/api/v1/emulators/${slug}/sandbox`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      })
      await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
    } finally {
      setSandboxSaving(false)
    }
  }

  async function handleDelete() {
    if (!slug || !entry) return
    if (!window.confirm(`Remove "${entry.name}"? This unregisters the binary but does not delete files.`)) return
    try {
      const { token } = await apiFetch<{ token: string }>(`/api/v1/emulators/${slug}/confirm-token`)
      await apiFetch(`/api/v1/emulators/${slug}`, {
        method: 'DELETE',
        body: JSON.stringify({ confirmation_token: token }),
      })
      await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
      navigate('/emulators')
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Remove failed.')
    }
  }

  async function handleRunInstaller() {
    if (!slug) return
    setIsInstalling(true)
    setInstallError(null)
    try {
      await apiFetch(`/api/v1/emulators/${slug}/install`, { method: 'POST' })
    } catch (err) {
      setIsInstalling(false)
      setInstallError(err instanceof ApiError ? err.detail : 'Failed to launch installer.')
    }
  }

  async function handleCloneRomPack() {
    if (!romPackSlug) return
    setIsCloning(true)
    setCloneError(null)
    try {
      await apiFetch(`/api/v1/emulators/${romPackSlug}/install`, { method: 'POST' })
    } catch (err) {
      setIsCloning(false)
      setCloneError(err instanceof ApiError ? err.detail : 'Failed to start clone.')
    }
  }

  if (catalog.length > 0 && !entry) {
    return (
      <div className="p-6" style={{ color: 'var(--fg-3)' }}>
        Emulator not found.
      </div>
    )
  }

  const BTN: React.CSSProperties = {
    border: 'none', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
    padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer',
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button
          type="button"
          onClick={() => navigate('/emulators')}
          style={{
            background: 'transparent', border: 0, color: 'var(--fg-1)',
            fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 500,
            cursor: 'pointer', padding: '6px 10px',
          }}
        >
          ← Emulators
        </button>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          onClick={handleDelete}
          style={{ ...BTN, background: 'transparent', border: '1px solid var(--error)', color: 'var(--error)' }}
        >
          Remove
        </button>
      </TopBar>

      <div className="p-6">
        {/* Header */}
        <div className="flex items-center gap-3.5 mb-1.5">
          <div
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              width: 56, height: 56,
              background: 'var(--surface-2)', border: '1px solid var(--border-strong)',
              fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 22, color: 'var(--peach-300)',
            }}
          >
            {entry ? entry.name.slice(0, 2).toUpperCase() : '??'}
          </div>
          <div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, letterSpacing: '-0.02em', margin: 0, color: 'var(--fg-1)' }}>
              {entry?.name ?? slug}
            </h1>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-3)', marginTop: 6 }}>
              {entry?.version}
            </div>
          </div>
          <span style={{ flex: 1 }} />
          <div className="flex gap-1.5">
            {eras.map((era) => (
              <span
                key={era}
                style={{
                  fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11,
                  letterSpacing: '0.08em', padding: '4px 6px', borderRadius: 'var(--r-1)',
                  border: `1px solid ${ERA_COLOR[era] ?? 'var(--border)'}`,
                  color: ERA_COLOR[era] ?? 'var(--fg-3)', display: 'inline-block',
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
          {romPackSlug && (
            <TabBtn id="rom" label="ROM Packs" active={tab === 'rom'} onClick={() => setTab('rom')} />
          )}
          <TabBtn id="ext" label="Extensions" active={tab === 'ext'} onClick={() => setTab('ext')} />
          <TabBtn id="profiles" label="Profiles" count={emulatorProfiles.length} active={tab === 'profiles'} onClick={() => setTab('profiles')} />
          {(entry?.known_limitations?.length ?? 0) > 0 && (
            <TabBtn id="limits" label="Known Limitations" count={entry!.known_limitations!.length} active={tab === 'limits'} onClick={() => setTab('limits')} />
          )}
        </div>

        {/* Overview tab */}
        {tab === 'overview' && entry && (
          <div>
            <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 12 }}>
                  Configuration
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)', width: 140, flexShrink: 0 }}>
                    Executable
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
                    {entry.install_path ?? '—'}
                  </span>
                </div>
                <KVTable rows={[
                  { label: 'Version',      value: entry.version },
                  { label: 'Install type', value: entry.install_type },
                  { label: 'Eras',         value: eras.join(' · ') || '—' },
                  { label: 'Status',       value: isReady ? 'Ready' : 'Not installed' },
                ]} />
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 4 }}>
                    Sandbox
                  </div>
                  {entry.container_hardcap_disabled === true ? (
                    <div style={{
                      padding: '8px 10px', borderBottom: '1px solid var(--border)',
                      background: 'rgba(239,68,68,0.06)', borderRadius: 'var(--r-1)',
                      marginBottom: 2,
                    }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: '#ef4444', lineHeight: 1.5 }}>
                        AppContainer isolation is not supported for this emulator. This is a permanent platform limitation.{' '}
                        <button
                          type="button"
                          onClick={() => setTab('limits')}
                          style={{ background: 'none', border: 'none', padding: 0, color: 'var(--peach-400)', textDecoration: 'underline', cursor: 'pointer', fontFamily: 'var(--font-display)', fontSize: 12 }}
                        >
                          Known Limitations
                        </button>
                        {' · '}
                        <a
                          href="https://www.qemu.org/docs/master/system/security.html"
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: 'var(--peach-400)', textDecoration: 'underline' }}
                        >
                          Learn more
                        </a>
                      </div>
                    </div>
                  ) : (
                    <SandboxToggle
                      label="AppContainer"
                      value={entry.container_enabled ?? false}
                      disabled={sandboxSaving}
                      onChange={(v) => handleSandboxToggle('container_enabled', v)}
                    />
                  )}
                  <SandboxToggle
                    label="CPU limit enabled"
                    value={!(entry.skip_cpu_limit ?? false)}
                    disabled={sandboxSaving}
                    onChange={(v) => handleSandboxToggle('skip_cpu_limit', !v)}
                  />
                  <SandboxToggle
                    label="Memory limit enabled"
                    value={!(entry.skip_memory_limit ?? false)}
                    disabled={sandboxSaving}
                    onChange={(v) => handleSandboxToggle('skip_memory_limit', !v)}
                  />
                </div>
                {/* Install actions for installer-type emulators */}
                {entry.install_type === 'installer' && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
                        <StatusDot ok={entry.installer_present} />
                        {entry.installer_present ? 'Installer ready' : 'Installer not placed'}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
                        <StatusDot ok={!!isReady} />
                        {isReady ? 'Installed' : isInstalling ? 'Waiting for install…' : 'Not installed'}
                      </div>
                      {entry.installer_present && !isReady && (
                        <button
                          type="button"
                          onClick={handleRunInstaller}
                          disabled={isInstalling}
                          style={{ ...BTN, background: 'var(--peach-500)', color: '#fff', opacity: isInstalling ? 0.5 : 1 }}
                        >
                          {isInstalling ? 'Running…' : 'Run Installer'}
                        </button>
                      )}
                    </div>
                    {!entry.installer_present && (
                      <GuidanceNote text={entry.guidance_text} url={entry.guidance_url} />
                    )}
                    {installError && (
                      <div style={{ marginTop: 6, fontSize: 12, color: 'var(--error)', fontFamily: 'var(--font-display)' }}>
                        {installError}
                      </div>
                    )}
                  </div>
                )}
                {/* Guidance for zip-type emulators not yet installed */}
                {entry.install_type === 'zip' && !isReady && entry.guidance_text && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                    <GuidanceNote text={entry.guidance_text} url={entry.guidance_url} />
                  </div>
                )}
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

            {/* Required BIOS assets */}
            {emulatorBios.length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 10 }}>
                  Required Assets
                </div>
                <div className="rounded-xl" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
                  {emulatorBios.map((bios, i) => (
                    <div
                      key={bios.slug}
                      style={{ padding: '14px 18px', borderBottom: i < emulatorBios.length - 1 ? '1px solid var(--border)' : 'none' }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
                          {bios.name}
                        </span>
                        <span style={{
                          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)',
                          border: '1px solid var(--border)', borderRadius: 'var(--r-1)', padding: '2px 6px',
                        }}>
                          required
                        </span>
                        <StatusDot ok={bios.is_present} />
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginBottom: 6 }}>
                        {bios.bios_path}/
                      </div>
                      {bios.is_present ? (
                        <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: '#4ade80' }}>
                          Files detected
                        </div>
                      ) : (
                        <GuidanceNote text={bios.guidance_text} url={bios.guidance_url} />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ROM Packs tab */}
        {tab === 'rom' && (
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
                      onClick={handleCloneRomPack}
                      disabled={isCloning}
                      style={{ ...BTN, background: 'var(--peach-500)', color: '#fff', opacity: isCloning ? 0.5 : 1 }}
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
        )}

        {/* Known Limitations tab */}
        {tab === 'limits' && entry && (
          <div className="flex flex-col gap-3">
            {(entry.known_limitations ?? []).map((lim, i) => {
              const { title: limTitle, severity: limSeverity, description: limDescription } = lim as { title: string; severity: string; description: string }
              const severityStyle: React.CSSProperties =
                limSeverity === 'warning'
                  ? { background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)', color: '#fbbf24' }
                  : limSeverity === 'critical'
                  ? { background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.35)', color: '#ef4444' }
                  : { background: 'var(--surface-1)', border: '1px solid var(--border)', color: 'var(--fg-3)' }
              return (
                <div key={i} className="rounded-xl p-[18px]" style={{ background: severityStyle.background, border: severityStyle.border }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>
                      {limTitle}
                    </span>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
                      letterSpacing: '0.08em', textTransform: 'uppercase',
                      padding: '2px 6px', borderRadius: 'var(--r-1)',
                      border: `1px solid ${severityStyle.color}`,
                      color: severityStyle.color,
                    }}>
                      {limSeverity}
                    </span>
                  </div>
                  <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, lineHeight: 1.55, color: 'var(--fg-2)', margin: 0 }}>
                    {limDescription}
                  </p>
                </div>
              )
            })}
          </div>
        )}

        {/* Profiles tab */}
        {tab === 'profiles' && (
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
                  onClick={() => navigate(`/profiles/${p.slug}`)}
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
        )}
      </div>
    </div>
  )
}
