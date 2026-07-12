import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import { EMULATOR_ERA_MAP, ERA_COLOR } from '@/types/era'
import type { EmulatorStatusData } from '@/pages/FirstRun/types'
import type { components } from '@shared/types'
import { TabBtn, type Tab } from './components/EmulatorDetailPrimitives'
import { OverviewTab } from './components/OverviewTab'
import { RomPackTab } from './components/RomPackTab'
import { ExtensionsTab } from './components/ExtensionsTab'
import { LimitationsTab } from './components/LimitationsTab'
type CatalogEntry = components['schemas']['CatalogEntryResponse']
type LaunchProfile = components['schemas']['ProfileItemRead']
type BiosItem = components['schemas']['BiosItem']


const EMULATOR_BIOS_PLATFORM: Record<string, string> = {
  'duckstation': 'ps1',
  'pcsx2':       'ps2',
  'xemu':        'xbox',
  'flycast':     'dreamcast',
  '86box':       '86box',
  'mesen':       'mesen',
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
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulator-items'),
    staleTime: 10_000,
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: async () => (await apiFetch<{ items: LaunchProfile[] }>('/api/v1/profile-items?limit=200')).items,
  })

  const entry = catalog.find((e) => e.slug === slug)
  const romPackSlug = entry?.rom_pack_slug ?? undefined
  const emulatorBiosPlatform = slug ? EMULATOR_BIOS_PLATFORM[slug] : undefined

  // Lookup-only consumer of GET /api/v1/bios (now Page[BiosItem]) —
  // unwraps .items, capped at limit=200 (same pattern as the /api/v1/profile-items
  // lookup consumers), not expected to exceed that at current catalog scale.
  const { data: allBios = [] } = useQuery<BiosItem[]>({
    queryKey: ['bios-requirements'],
    queryFn: async () => (await apiFetch<{ items: BiosItem[] }>('/api/v1/bios?limit=200')).items,
    enabled: !!emulatorBiosPlatform,
  })

  const { data: installStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulator-items/${slug}/status`),
    refetchInterval: isInstalling ? 3000 : false,
    enabled: isInstalling && !!slug,
  })

  const { data: cloneStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', romPackSlug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulator-items/${romPackSlug}/status`),
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
      await apiFetch(`/api/v1/emulator-items/${slug}/sandbox`, {
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
      const { token } = await apiFetch<{ token: string }>(`/api/v1/emulator-items/${slug}/confirm-token`)
      await apiFetch(`/api/v1/emulator-items/${slug}`, {
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
      await apiFetch(`/api/v1/emulator-items/${slug}/install`, { method: 'POST' })
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
      await apiFetch(`/api/v1/emulator-items/${romPackSlug}/install`, { method: 'POST' })
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
          {(entry?.known_limitations?.length ?? 0) > 0 && (
            <TabBtn id="limits" label="Known Limitations" count={entry!.known_limitations!.length} active={tab === 'limits'} onClick={() => setTab('limits')} />
          )}
        </div>

        {tab === 'overview' && entry && (
          <OverviewTab
            entry={entry}
            eras={eras}
            isReady={isReady}
            emulatorProfilesCount={emulatorProfiles.length}
            emulatorBios={emulatorBios}
            sandboxSaving={sandboxSaving}
            onSandboxToggle={handleSandboxToggle}
            onShowLimitations={() => setTab('limits')}
            isInstalling={isInstalling}
            installError={installError}
            onRunInstaller={handleRunInstaller}
            romPackEntry={romPackEntry}
            isCloning={isCloning}
            cloneError={cloneError}
            onCloneRomPack={handleCloneRomPack}
          />
        )}

        {tab === 'rom' && (
          <RomPackTab
            romPackEntry={romPackEntry}
            isCloning={isCloning}
            cloneError={cloneError}
            onCloneRomPack={handleCloneRomPack}
          />
        )}

        {tab === 'ext' && <ExtensionsTab entry={entry} />}

        {tab === 'limits' && entry && <LimitationsTab entry={entry} />}
      </div>
    </div>
  )
}
