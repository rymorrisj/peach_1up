import { GuidanceNote, KVTable, SandboxToggle, StatusDot } from './EmulatorDetailPrimitives'
import { BiosPlaceAction } from './BiosPlaceAction'
import { CloneRomPackButton } from './CloneRomPackButton'
import type { BiosRequirement } from '@/pages/FirstRun/types'
import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

interface OverviewTabProps {
  entry: CatalogEntry
  eras: string[]
  isReady: boolean | string | null | undefined
  emulatorProfilesCount: number
  emulatorBios: BiosRequirement[]
  sandboxSaving: boolean
  onSandboxToggle: (field: 'container_enabled' | 'skip_cpu_limit' | 'skip_memory_limit', value: boolean) => void
  onShowLimitations: () => void
  isInstalling: boolean
  installError: string | null
  onRunInstaller: () => void
  romPackEntry: CatalogEntry | undefined
  isCloning: boolean
  cloneError: string | null
  onCloneRomPack: () => void
}

export function OverviewTab({
  entry, eras, isReady, emulatorProfilesCount, emulatorBios, sandboxSaving, onSandboxToggle,
  onShowLimitations, isInstalling, installError, onRunInstaller,
  romPackEntry, isCloning, cloneError, onCloneRomPack,
}: OverviewTabProps) {
  return (
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
                    onClick={onShowLimitations}
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
                onChange={(v) => onSandboxToggle('container_enabled', v)}
              />
            )}
            <SandboxToggle
              label="CPU limit enabled"
              value={!(entry.skip_cpu_limit ?? false)}
              disabled={sandboxSaving}
              onChange={(v) => onSandboxToggle('skip_cpu_limit', !v)}
            />
            <SandboxToggle
              label="Memory limit enabled"
              value={!(entry.skip_memory_limit ?? false)}
              disabled={sandboxSaving}
              onChange={(v) => onSandboxToggle('skip_memory_limit', !v)}
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
                    onClick={onRunInstaller}
                    disabled={isInstalling}
                    style={{
                      border: 'none', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600,
                      padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer',
                      background: 'var(--peach-500)', color: '#fff', opacity: isInstalling ? 0.5 : 1,
                    }}
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
              { value: String(emulatorProfilesCount), label: 'profiles' },
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
                    {bios.required ? 'required' : 'optional'}
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
                {bios.slug === '86box-roms' && romPackEntry ? (
                  <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 6 }}>
                    <div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.04em', color: 'var(--fg-3)', marginBottom: 4 }}>
                        Clone official ROM pack
                      </div>
                      {romPackEntry.is_installed && (
                        <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: '#4ade80' }}>
                          Installed
                        </span>
                      )}
                      <CloneRomPackButton
                        romPackEntry={romPackEntry}
                        isCloning={isCloning}
                        cloneError={cloneError}
                        onClone={onCloneRomPack}
                        compact
                      />
                    </div>
                    <div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.04em', color: 'var(--fg-3)', marginBottom: 4 }}>
                        Locate folder you already have
                      </div>
                      <BiosPlaceAction bios={bios} />
                    </div>
                  </div>
                ) : (
                  <BiosPlaceAction bios={bios} />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
