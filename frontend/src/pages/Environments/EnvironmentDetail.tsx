import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import { ERA_LABELS } from '@/generated/constants'
import type { components } from '@shared/types'

type Platform = components['schemas']['PlatformRead']
type Snapshot = components['schemas']['SnapshotRead']

const ERA_COLOR: Record<string, string> = {
  DOS: 'var(--era-dos)', WIN31: 'var(--era-win31)', WIN95: 'var(--era-win95)',
  WIN98: 'var(--era-win98)', WINXP: 'var(--era-winxp)', PS1: '#a9a0d6',
  PS2: '#6090d0', XBOX: '#6db36d', DC: '#d0a060', NES: '#d06060', N64: '#60a0d0',
}

type Tab = 'overview' | 'snapshots' | 'notes'

function TabBtn({ label, active, onClick, count }: {
  label: string; active: boolean; onClick: () => void; count?: number
}) {
  return (
    <button type="button" onClick={onClick} style={{
      padding: '10px 14px', border: 0, background: 'transparent',
      borderBottom: active ? '2px solid var(--peach-500)' : '2px solid transparent',
      color: active ? 'var(--fg-1)' : 'var(--fg-3)',
      fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13,
      lineHeight: 1, cursor: 'pointer', marginBottom: -1,
    }}>
      {label}
      {count != null && (
        <span style={{ opacity: 0.55, marginLeft: 6, fontFamily: 'var(--font-mono)' }}>{count}</span>
      )}
    </button>
  )
}

function ReadRow({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return (
    <div className="flex items-center px-[18px] py-3.5"
      style={{ borderBottom: last ? 'none' : '1px solid var(--border)', gap: 12 }}>
      <div style={{ minWidth: 190, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
        {label}
      </div>
      <div style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', textAlign: 'right', wordBreak: 'break-all' }}>
        {value}
      </div>
    </div>
  )
}

function EditRow({ label, children, last = false }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className="flex items-center px-[18px] py-2.5"
      style={{ borderBottom: last ? 'none' : '1px solid var(--border)', gap: 12 }}>
      <div style={{ minWidth: 190, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
        {label}
      </div>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  )
}

const INPUT: React.CSSProperties = {
  width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
  borderRadius: 'var(--r-2)', padding: '7px 10px', fontFamily: 'var(--font-mono)',
  fontSize: 12, color: 'var(--fg-1)', outline: 'none',
}

export default function EnvironmentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState({
    name: '', era: '', emulator_slug: '', base_image_path: '', working_image_path: '', config_path: '',
  })
  const [editSaving, setEditSaving] = useState(false)
  const [editSaveError, setEditSaveError] = useState<string | null>(null)

  const { data: platform } = useQuery<Platform>({
    queryKey: ['platform', id],
    queryFn: () => apiFetch<Platform>(`/api/v1/platforms/${id}`),
    enabled: !!id,
  })

  const { data: snapshots = [] } = useQuery<Snapshot[]>({
    queryKey: ['platform-snapshots', id],
    queryFn: () => apiFetch<Snapshot[]>(`/api/v1/platforms/${id}/snapshots`),
    enabled: !!id,
  })

  useEffect(() => { if (platform) setNotes(platform.notes ?? '') }, [platform?.id])

  async function handleSaveNotes() {
    if (!platform) return
    setSaving(true); setSaveError(null); setSaved(false)
    try {
      await apiFetch(`/api/v1/platforms/${platform.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ notes: notes.trim() || null }),
      })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  function startEditing() {
    if (!platform) return
    setEditForm({
      name: platform.name,
      era: platform.era,
      emulator_slug: platform.emulator_slug,
      base_image_path: platform.base_image_path ?? '',
      working_image_path: platform.working_image_path ?? '',
      config_path: platform.config_path ?? '',
    })
    setEditSaveError(null)
    setTab('overview')
    setEditing(true)
  }

  async function handleEditSave() {
    if (!platform) return
    setEditSaving(true); setEditSaveError(null)
    try {
      await apiFetch(`/api/v1/platforms/${platform.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: editForm.name.trim(),
          era: editForm.era,
          emulator_slug: editForm.emulator_slug.trim(),
          base_image_path: editForm.base_image_path.trim() || null,
          working_image_path: editForm.working_image_path.trim() || null,
          config_path: editForm.config_path.trim() || null,
        }),
      })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
      await queryClient.invalidateQueries({ queryKey: ['platform', id] })
      setEditing(false)
    } catch (err) {
      setEditSaveError(err instanceof ApiError ? err.detail : 'Save failed.')
    } finally {
      setEditSaving(false)
    }
  }

  function setField(key: keyof typeof editForm, value: string) {
    setEditForm(f => ({ ...f, [key]: value }))
  }

  async function handleLaunch() {
    if (!platform) return
    setLaunching(true)
    try {
      await apiFetch(`/api/v1/environments/${platform.id}/launch`, { method: 'POST' })
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Launch failed.')
    } finally {
      setLaunching(false)
    }
  }

  if (!platform) {
    return <div className="p-6" style={{ color: 'var(--fg-3)' }}>Loading…</div>
  }

  const eraKey = platform.era.toUpperCase()
  const eraColor = ERA_COLOR[eraKey] ?? 'var(--fg-3)'
  const statusColor = platform.status === 'ready' ? 'var(--success)' : platform.status === 'degraded' ? 'var(--error)' : 'var(--fg-3)'
  const statusLabel = platform.status === 'ready' ? 'Ready' : platform.status === 'degraded' ? 'Degraded' : (platform.status ?? 'Unknown')
  const BTN: React.CSSProperties = { border: 'none', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer' }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button type="button" onClick={() => navigate('/environments')}
          style={{ background: 'transparent', border: 0, color: 'var(--fg-1)', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 500, cursor: 'pointer', padding: '6px 10px' }}>
          ← Environments
        </button>
        <span style={{ flex: 1 }} />
        {!editing && (
          <button type="button" onClick={handleLaunch} disabled={launching}
            style={{ ...BTN, background: 'var(--peach-500)', color: '#1d0a04' }}>
            {launching ? 'Launching…' : 'Launch'}
          </button>
        )}
        {editing ? (
          <>
            <button type="button" onClick={() => setEditing(false)}
              style={{ ...BTN, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>
              Cancel
            </button>
            <button type="button" onClick={handleEditSave} disabled={editSaving}
              style={{ ...BTN, background: 'var(--peach-500)', color: '#1d0a04' }}>
              {editSaving ? 'Saving…' : 'Save'}
            </button>
          </>
        ) : (
          <button type="button" onClick={startEditing}
            style={{ ...BTN, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>
            Edit
          </button>
        )}
      </TopBar>

      <div className="p-6">
        <div className="flex items-center gap-3 mb-4">
          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, letterSpacing: '-0.02em', margin: 0, color: 'var(--fg-1)' }}>
            {platform.name}
          </h1>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', padding: '4px 6px', borderRadius: 'var(--r-1)', border: `1px solid ${eraColor}`, color: eraColor }}>
            {eraKey}
          </span>
        </div>

        <div className="flex gap-0" style={{ borderBottom: '1px solid var(--border)', marginBottom: 22 }}>
          <TabBtn label="Overview" active={tab === 'overview'} onClick={() => setTab('overview')} />
          <TabBtn label="Snapshots" active={tab === 'snapshots'} onClick={() => setTab('snapshots')} count={snapshots.length} />
          <TabBtn label="Notes" active={tab === 'notes'} onClick={() => setTab('notes')} />
        </div>

        <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 280px' }}>
          <div>
            {tab === 'overview' && (
              <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
                <div style={{ padding: '14px 18px 8px', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)' }}>
                  Configuration
                </div>
                {editing ? (
                  <>
                    <EditRow label="Name">
                      <input value={editForm.name} onChange={e => setField('name', e.target.value)} style={INPUT} />
                    </EditRow>
                    <EditRow label="Era">
                      <select value={editForm.era} onChange={e => setField('era', e.target.value)} style={INPUT}>
                        {Object.entries(ERA_LABELS).map(([k, v]) => (
                          <option key={k} value={k}>{v}</option>
                        ))}
                      </select>
                    </EditRow>
                    <EditRow label="Emulator backend">
                      <input value={editForm.emulator_slug} onChange={e => setField('emulator_slug', e.target.value)} style={INPUT} />
                    </EditRow>
                    <EditRow label="Base image path">
                      <input value={editForm.base_image_path} onChange={e => setField('base_image_path', e.target.value)} style={INPUT} placeholder="optional" />
                    </EditRow>
                    <EditRow label="Working image path">
                      <input value={editForm.working_image_path} onChange={e => setField('working_image_path', e.target.value)} style={INPUT} placeholder="optional" />
                    </EditRow>
                    <EditRow label="Config path" last>
                      <input value={editForm.config_path} onChange={e => setField('config_path', e.target.value)} style={INPUT} placeholder="optional" />
                    </EditRow>
                    {editSaveError && (
                      <div className="px-[18px] py-3" style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--error)' }}>
                        ❌ {editSaveError}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <ReadRow label="Name" value={platform.name} />
                    <ReadRow label="Era" value={eraKey} />
                    <ReadRow label="Emulator backend" value={platform.emulator_slug} />
                    <ReadRow label="Base image path" value={platform.base_image_path ?? '—'} />
                    <ReadRow label="Working image path" value={platform.working_image_path ?? '—'} />
                    <ReadRow label="Config path" value={platform.config_path ?? '—'} last />
                  </>
                )}
              </div>
            )}

            {tab === 'snapshots' && (
              <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
                <div className="grid px-[18px] py-2.5" style={{
                  gridTemplateColumns: '1fr 140px 90px', fontFamily: 'var(--font-mono)', fontWeight: 500,
                  fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)',
                  borderBottom: '1px solid var(--border)',
                }}>
                  <span>Name</span><span>Date</span><span style={{ textAlign: 'right' }}>Size</span>
                </div>
                {snapshots.length === 0 ? (
                  <div style={{ padding: '16px 18px', fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
                    No snapshots yet.
                  </div>
                ) : snapshots.map((s, i) => (
                  <div key={s.id} className="grid px-[18px] py-3.5" style={{
                    gridTemplateColumns: '1fr 140px 90px', alignItems: 'center',
                    borderBottom: i < snapshots.length - 1 ? '1px solid var(--border)' : 'none',
                  }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>{s.name}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{new Date(s.created_at).toLocaleDateString()}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)', textAlign: 'right' }}>
                      {s.size_bytes != null ? `${(s.size_bytes / 1_048_576).toFixed(1)} MB` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {tab === 'notes' && (
              <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={8}
                  placeholder="Notes about this environment…"
                  style={{ width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--r-2)', padding: '10px 12px', fontFamily: 'var(--font-display)', fontSize: 13, lineHeight: 1.5, color: 'var(--fg-1)', outline: 'none', resize: 'vertical' }} />
                {saveError && (
                  <div className="mt-2" style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--error)' }}>❌ {saveError}</div>
                )}
                <div className="flex justify-end mt-3">
                  <button type="button" onClick={handleSaveNotes} disabled={saving}
                    style={{ ...BTN, background: 'var(--peach-500)', color: '#1d0a04' }}>
                    {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save Notes'}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-3.5">
            <div className="rounded-xl p-[18px]" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)', marginBottom: 14 }}>
                At a glance
              </div>
              <div className="flex items-center gap-2 mb-3.5">
                <span className="rounded-full inline-block shrink-0" style={{ width: 7, height: 7, background: statusColor }} />
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>{statusLabel}</span>
              </div>
              {[
                { label: 'emulator', value: platform.emulator_slug },
                { label: 'last check', value: platform.last_health_check ? new Date(platform.last_health_check).toLocaleDateString() : '—' },
                { label: 'snapshots', value: String(snapshots.length) },
              ].map(({ label, value }) => (
                <div key={label} className="mb-3 last:mb-0">
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15, lineHeight: 1, color: 'var(--fg-1)' }}>{value}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 3 }}>{label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
