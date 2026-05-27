import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import type { components } from '@shared/types'

type LaunchProfile = components['schemas']['ProfileRead']
type LibraryItem = components['schemas']['LibraryItemRead']

const ERA_COLOR: Record<string, string> = {
  DOS: 'var(--era-dos)', WIN31: 'var(--era-win31)', WIN95: 'var(--era-win95)',
  WIN98: 'var(--era-win98)', WINXP: 'var(--era-winxp)', PS1: '#a9a0d6',
  PS2: '#6090d0', XBOX: '#6db36d', DC: '#d0a060', NES: '#d06060', N64: '#60a0d0',
}

type Tab = 'identity' | 'emulator' | 'media' | 'performance' | 'library'

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className="relative inline-flex shrink-0 items-center rounded-full transition-colors duration-[120ms] focus:outline-none"
      style={{ width: 36, height: 20, background: checked ? 'var(--peach-500)' : 'var(--surface-3)', border: 'none', cursor: 'pointer', padding: 0 }}>
      <span className="absolute inline-block rounded-full transition-all duration-[120ms]"
        style={{ width: 16, height: 16, top: 2, left: checked ? 18 : 2, background: checked ? '#1d0a04' : 'var(--fg-3)' }} />
    </button>
  )
}

function TabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={{
      padding: '10px 14px', border: 0, background: 'transparent',
      borderBottom: active ? '2px solid var(--peach-500)' : '2px solid transparent',
      color: active ? 'var(--fg-1)' : 'var(--fg-3)',
      fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13, lineHeight: 1, cursor: 'pointer', marginBottom: -1,
    }}>{label}</button>
  )
}

function FieldRow({ label, hint, children, last = false }: {
  label: string; hint?: string; children: React.ReactNode; last?: boolean
}) {
  return (
    <div className="flex items-center px-[18px] py-3.5"
      style={{ borderBottom: last ? 'none' : '1px solid var(--border)', gap: 12 }}>
      <div style={{ minWidth: 200 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 13, color: 'var(--fg-1)' }}>{label}</div>
        {hint && <div style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{hint}</div>}
      </div>
      <div className="flex flex-1 items-center justify-end"
        style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', minWidth: 0 }}>
        {children}
      </div>
    </div>
  )
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl overflow-hidden mb-3.5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
      <div style={{ padding: '14px 18px 8px', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)' }}>
        {title}
      </div>
      {children}
    </div>
  )
}

const INPUT_STYLE: React.CSSProperties = {
  background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--r-2)',
  padding: '7px 10px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)',
  outline: 'none', width: '100%', minWidth: 200,
}

export default function ProfileDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('identity')
  const [name, setName] = useState('')
  const [enableNetworking, setEnableNetworking] = useState(false)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const profile = profiles.find((p) => p.slug === slug)

  const { data: items = [] } = useQuery<LibraryItem[]>({
    queryKey: ['profile-items', slug],
    queryFn: () => apiFetch<LibraryItem[]>(`/api/v1/profiles/${slug}/items`),
    enabled: !!slug,
  })

  useEffect(() => {
    if (!profile) return
    setName(profile.name)
    setEnableNetworking(profile.enable_networking)
    setNotes(profile.notes ?? '')
  }, [profile?.slug])

  async function handleSave() {
    if (!profile) return
    setSaving(true); setSaveError(null); setSaved(false)
    try {
      const updated = await apiFetch<LaunchProfile>(`/api/v1/profiles/${profile.slug}`, {
        method: 'PATCH',
        body: JSON.stringify({ name: name.trim(), enable_networking: enableNetworking, notes: notes.trim() || null }),
      })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      navigate(`/profiles/${updated.slug}`, { replace: true })
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  async function handleDuplicate() {
    if (!profile) return
    try {
      const created = await apiFetch<LaunchProfile>('/api/v1/profiles', {
        method: 'POST',
        body: JSON.stringify({
          name: profile.name + ' (copy)',
          slug: profile.slug + '-copy',
          emulator_slug: profile.emulator_slug,
          era: profile.era,
          enable_networking: profile.enable_networking,
          notes: profile.notes,
        }),
      })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      navigate(`/profiles/${created.slug}`)
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Duplicate failed. The slug may already exist.')
    }
  }

  async function handleDelete() {
    if (!profile || profile.is_bundled) return
    if (!window.confirm(`Delete profile "${profile.name}"? This cannot be undone.`)) return
    try {
      await apiFetch(`/api/v1/profiles/${profile.slug}`, { method: 'DELETE' })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      navigate('/profiles')
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Delete failed.')
    }
  }

  if (profiles.length > 0 && !profile) {
    return <div className="p-6" style={{ color: 'var(--fg-3)' }}>Profile not found.</div>
  }
  if (!profile) {
    return <div className="p-6" style={{ color: 'var(--fg-3)' }}>Loading…</div>
  }

  const eraKey = profile.era.toUpperCase()
  const eraColor = ERA_COLOR[eraKey] ?? 'var(--fg-3)'
  const BTN: React.CSSProperties = { border: 'none', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer' }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button type="button" onClick={() => navigate('/profiles')}
          style={{ background: 'transparent', border: 0, color: 'var(--fg-1)', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 500, cursor: 'pointer', padding: '6px 10px' }}>
          ← Profiles
        </button>
        <span style={{ flex: 1 }} />
        <button type="button" onClick={handleDuplicate}
          style={{ ...BTN, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>
          Duplicate
        </button>
        <button type="button" onClick={handleSave} disabled={saving}
          style={{ ...BTN, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save'}
        </button>
        <button type="button"
          style={{ ...BTN, background: 'var(--peach-500)', color: '#1d0a04', opacity: 0.5, cursor: 'not-allowed' }}
          title="Requires a bound software item">
          Launch
        </button>
      </TopBar>

      <div className="p-6">
        <div className="flex items-center gap-3 mb-4">
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', padding: '4px 6px', borderRadius: 'var(--r-1)', border: `1px solid ${eraColor}`, color: eraColor }}>
            {eraKey}
          </span>
          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, letterSpacing: '-0.02em', margin: 0, color: 'var(--fg-1)' }}>
            {profile.name}
          </h1>
        </div>

        {saveError && (
          <div className="mb-4 rounded-md px-3 py-2.5" style={{ borderLeft: '3px solid var(--error)', background: 'rgb(255 106 85 / 0.08)', fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--error)' }}>
            ❌ {saveError}
          </div>
        )}

        <div className="flex gap-0" style={{ borderBottom: '1px solid var(--border)', marginBottom: 22 }}>
          <TabBtn label="Identity" active={tab === 'identity'} onClick={() => setTab('identity')} />
          <TabBtn label="Emulator" active={tab === 'emulator'} onClick={() => setTab('emulator')} />
          <TabBtn label="Media" active={tab === 'media'} onClick={() => setTab('media')} />
          <TabBtn label="Performance" active={tab === 'performance'} onClick={() => setTab('performance')} />
          <TabBtn label="Library" active={tab === 'library'} onClick={() => setTab('library')} />
        </div>

        <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 300px' }}>
          <div>
            {tab === 'identity' && (
              <SectionCard title="Identity">
                <FieldRow label="Profile name">
                  <input value={name} onChange={(e) => setName(e.target.value)} style={INPUT_STYLE} />
                </FieldRow>
                <FieldRow label="Bound software">
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
                <FieldRow label="Profile ID" last>
                  <span>{profile.id}</span>
                </FieldRow>
              </SectionCard>
            )}

            {tab === 'emulator' && (
              <SectionCard title="Emulator">
                <FieldRow label="Backend">
                  <span>{profile.emulator_slug}</span>
                </FieldRow>
                <FieldRow label="Era / OS image">
                  <span style={{ textTransform: 'uppercase' }}>{profile.era}</span>
                </FieldRow>
                <FieldRow label="Hardware accuracy" hint="High-accuracy machine emulation">
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
                <FieldRow label="Working image path" last>
                  <span style={{ color: 'var(--fg-3)' }}>{profile.config_path ?? '—'}</span>
                </FieldRow>
              </SectionCard>
            )}

            {tab === 'media' && (
              <SectionCard title="Media">
                <FieldRow label="Primary disc path">
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
                <FieldRow label="HDD image">
                  {profile.drive_slug ? (
                    <button type="button" onClick={() => navigate(`/drives/${profile.drive_slug}`)}
                      style={{ background: 'none', border: 'none', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--peach-500)', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
                      {profile.drive_slug}
                    </button>
                  ) : (
                    <span style={{ color: 'var(--fg-3)' }}>—</span>
                  )}
                </FieldRow>
                <FieldRow label="Mounted ROM packs" last>
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
              </SectionCard>
            )}

            {tab === 'performance' && (
              <SectionCard title="Performance">
                <FieldRow label="Memory">
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
                <FieldRow label="CPU cycles" hint="auto, fixed-NNN, max, or native">
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
                <FieldRow label="Mouse capture">
                  <span style={{ color: 'var(--fg-3)' }}>—</span>
                </FieldRow>
                <FieldRow label="Network access" hint="Off enforces job-object isolation" last>
                  <span className="flex items-center gap-2">
                    <Toggle checked={enableNetworking} onChange={setEnableNetworking} />
                    <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)' }}>
                      {enableNetworking ? 'On — host bridge' : 'Blocked'}
                    </span>
                  </span>
                </FieldRow>
              </SectionCard>
            )}

            {tab === 'library' && (
              <SectionCard title="Bound items">
                {items.length === 0 ? (
                  <div className="px-[18px] py-4" style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
                    No library items bound to this profile.
                  </div>
                ) : items.map((item, i) => (
                  <div key={item.id} className="flex items-center px-[18px] py-3"
                    style={{ borderBottom: i < items.length - 1 ? '1px solid var(--border)' : 'none', gap: 12 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 13, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.title}
                      </div>
                      {item.year && (
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>{item.year}</div>
                      )}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>
                      {item.launch_count > 0 ? `${item.launch_count} launch${item.launch_count !== 1 ? 'es' : ''}` : 'never launched'}
                    </div>
                    <button type="button" onClick={() => navigate(`/library/${item.slug ?? item.id}`)}
                      style={{ background: 'none', border: 'none', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--peach-500)', cursor: 'pointer', padding: '4px 0', textDecoration: 'underline' }}>
                      View →
                    </button>
                  </div>
                ))}
              </SectionCard>
            )}
          </div>

          <div className="flex flex-col gap-3.5">
            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 14 }}>
                At a glance
              </div>
              {[
                { label: 'launches', value: profile.total_launches > 0 ? String(profile.total_launches) : '—' },
                { label: 'items', value: profile.item_count > 0 ? String(profile.item_count) : '—' },
                { label: 'last launch', value: profile.last_launched_at ? new Date(profile.last_launched_at).toLocaleDateString() : '—' },
              ].map(({ label, value }) => (
                <div key={label} className="mb-3.5">
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18, lineHeight: 1, color: 'var(--fg-1)' }}>{value}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 3 }}>{label}</div>
                </div>
              ))}
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 2 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 8 }}>Snapshots</div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--fg-3)', marginBottom: 10 }}>No snapshots.</div>
                <button type="button" disabled
                  style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600, padding: '8px 12px', borderRadius: 'var(--r-2)', cursor: 'not-allowed' }}>
                  Take snapshot
                </button>
              </div>
            </div>

            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 8 }}>
                Notes
              </div>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4}
                placeholder="Notes about this profile…"
                style={{ ...INPUT_STYLE, resize: 'vertical', fontFamily: 'var(--font-display)', fontSize: 13, lineHeight: 1.5 }} />
            </div>

            {!profile.is_bundled && (
              <button type="button" onClick={handleDelete}
                style={{ background: 'transparent', border: '1px solid var(--error)', color: 'var(--error)', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer', alignSelf: 'flex-start' }}>
                Delete profile
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
