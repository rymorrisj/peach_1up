import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import { ERA_LABELS } from '@/generated/constants'
import type { components } from '@shared/types'
type LaunchProfile = components['schemas']['ProfileRead']

const ERA_COLOR: Record<string, string> = {
  DOS:   'var(--era-dos)',
  WIN31: 'var(--era-win31)',
  WIN95: 'var(--era-win95)',
  WIN98: 'var(--era-win98)',
  WINXP: 'var(--era-winxp)',
}

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative inline-flex shrink-0 items-center rounded-full transition-colors duration-[120ms] focus:outline-none"
      style={{
        width: 36,
        height: 20,
        background: checked ? 'var(--peach-500)' : 'var(--surface-3)',
        border: 'none',
        cursor: 'pointer',
        padding: 0,
      }}
    >
      <span
        className="absolute inline-block rounded-full transition-all duration-[120ms]"
        style={{
          width: 16,
          height: 16,
          top: 2,
          left: checked ? 18 : 2,
          background: checked ? '#1d0a04' : 'var(--fg-3)',
        }}
      />
    </button>
  )
}

function FieldRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center px-[18px] py-3.5" style={{ borderBottom: '1px solid var(--border)', gap: 12 }}>
      <div style={{ minWidth: 200 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 13, lineHeight: 1.3, color: 'var(--fg-1)' }}>
          {label}
        </div>
        {hint && (
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 12, lineHeight: 1.4, color: 'var(--fg-3)', marginTop: 2 }}>
            {hint}
          </div>
        )}
      </div>
      <div className="flex flex-1 items-center justify-end" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', minWidth: 0 }}>
        {children}
      </div>
    </div>
  )
}

function SectionPanel({ title, children, last = false }: { title: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)', marginBottom: last ? 0 : 14 }}>
      <div style={{ padding: '14px 18px 8px', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)' }}>
        {title}
      </div>
      {children}
    </div>
  )
}

const INPUT_STYLE = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--r-2)',
  padding: '7px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--fg-1)',
  outline: 'none',
  width: '100%',
  minWidth: 200,
}

const SELECT_STYLE = {
  ...INPUT_STYLE,
}

export default function ProfileDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const profile = profiles.find((p) => String(p.id) === id)

  const [name, setName] = useState('')
  const [era, setEra] = useState('')
  const [emulatorSlug, setEmulatorSlug] = useState('')
  const [extraArgs, setExtraArgs] = useState('')
  const [enableNetworking, setEnableNetworking] = useState(false)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!profile) return
    setName(profile.name)
    setEra(profile.era)
    setEmulatorSlug(profile.emulator_slug)
    setExtraArgs(profile.extra_args ?? '')
    setEnableNetworking(profile.enable_networking)
    setNotes(profile.notes ?? '')
  }, [profile])

  async function handleSave() {
    if (!profile) return
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      await apiFetch(`/api/v1/profiles/${profile.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: name.trim(),
          era,
          emulator_slug: emulatorSlug.trim(),
          extra_args: extraArgs.trim() || null,
          enable_networking: enableNetworking,
          notes: notes.trim() || null,
        }),
      })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!profile) return
    if (!window.confirm(`Delete profile "${profile.name}"? This cannot be undone.`)) return
    try {
      await apiFetch(`/api/v1/profiles/${profile.id}`, { method: 'DELETE' })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      navigate('/profiles')
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Delete failed.')
    }
  }

  if (profiles.length > 0 && !profile) {
    return <div className="p-6" style={{ color: 'var(--fg-3)' }}>Profile not found.</div>
  }

  const eraKey = (profile?.era ?? era).toUpperCase()
  const eraColor = ERA_COLOR[eraKey] ?? 'var(--fg-3)'

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button
          type="button"
          onClick={() => navigate('/profiles')}
          style={{ background: 'transparent', border: 0, color: 'var(--fg-1)', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 500, cursor: 'pointer', padding: '6px 10px' }}
        >
          ← Profiles
        </button>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{ background: 'var(--peach-500)', border: 'none', color: '#1d0a04', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer' }}
        >
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save Changes'}
        </button>
      </TopBar>

      <div className="p-6">
        {/* Page title */}
        <div className="flex items-center gap-3.5 mb-5">
          {profile && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontWeight: 600,
                fontSize: 11,
                letterSpacing: '0.08em',
                padding: '4px 6px',
                borderRadius: 'var(--r-1)',
                border: `1px solid ${eraColor}`,
                color: eraColor,
                display: 'inline-block',
                textTransform: 'uppercase',
              }}
            >
              {eraKey}
            </span>
          )}
          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, letterSpacing: '-0.02em', margin: 0, color: 'var(--fg-1)' }}>
            {profile?.name ?? 'Loading…'}
          </h1>
          {profile && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-3)' }}>
              ./profiles/{profile.slug}.toml
            </span>
          )}
        </div>

        {saveError && (
          <div className="mb-4 rounded-md px-3 py-2.5" style={{ borderLeft: '3px solid var(--error)', background: 'rgb(255 106 85 / 0.08)', fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--error)' }}>
            ❌ {saveError}
          </div>
        )}

        <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 320px' }}>
          {/* Left column */}
          <div className="flex flex-col gap-3.5">

            <SectionPanel title="Identity">
              <FieldRow label="Profile name">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={INPUT_STYLE}
                />
              </FieldRow>
              <FieldRow label="Profile slug">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
                  {profile?.slug}
                </span>
              </FieldRow>
              <div style={{ borderBottom: 'none' }}>
                <FieldRow label="Profile ID">
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
                    {profile?.id}
                  </span>
                </FieldRow>
              </div>
            </SectionPanel>

            <SectionPanel title="Emulator">
              <FieldRow label="Backend">
                <input
                  value={emulatorSlug}
                  onChange={(e) => setEmulatorSlug(e.target.value)}
                  style={INPUT_STYLE}
                  placeholder="dosbox-x"
                />
              </FieldRow>
              <FieldRow label="Era / OS">
                <select
                  value={era}
                  onChange={(e) => setEra(e.target.value)}
                  style={SELECT_STYLE}
                >
                  <option value="">— Select era —</option>
                  {ERA_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FieldRow>
              <div style={{ borderBottom: 'none' }}>
                <FieldRow label="Extra args" hint="Additional command-line flags">
                  <input
                    value={extraArgs}
                    onChange={(e) => setExtraArgs(e.target.value)}
                    style={INPUT_STYLE}
                    placeholder="-fullscreen"
                  />
                </FieldRow>
              </div>
            </SectionPanel>

            <SectionPanel title="Networking" last>
              <div style={{ borderBottom: 'none' }}>
                <FieldRow label="Network access" hint="Off enforces job-object isolation">
                  <span className="flex items-center gap-2">
                    <Toggle checked={enableNetworking} onChange={setEnableNetworking} />
                    <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)' }}>
                      {enableNetworking ? 'On — host bridge' : 'Blocked'}
                    </span>
                  </span>
                </FieldRow>
              </div>
            </SectionPanel>
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-3.5">
            {/* At a glance */}
            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 14 }}>
                At a glance
              </div>
              <div className="grid grid-cols-2 gap-3.5">
                {[
                  { value: profile ? new Date(profile.created_at).toLocaleDateString() : '—', label: 'created' },
                  { value: profile?.is_bundled ? 'default' : 'custom', label: 'type' },
                ].map(({ value, label }) => (
                  <div key={label}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18, lineHeight: 1, color: 'var(--fg-1)' }}>
                      {value}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 4 }}>
                      {label}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Notes */}
            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 8 }}>
                Notes
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={4}
                placeholder="Any notes about this profile…"
                style={{
                  ...INPUT_STYLE,
                  resize: 'vertical',
                  fontFamily: 'var(--font-display)',
                  fontSize: 13,
                  lineHeight: 1.5,
                }}
              />
            </div>

            {/* Danger zone */}
            {profile && !profile.is_bundled && (
              <button
                type="button"
                onClick={handleDelete}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--error)',
                  color: 'var(--error)',
                  fontFamily: 'var(--font-display)',
                  fontSize: 13,
                  fontWeight: 600,
                  padding: '9px 14px',
                  borderRadius: 'var(--r-2)',
                  cursor: 'pointer',
                  alignSelf: 'flex-start',
                }}
              >
                Delete profile
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
