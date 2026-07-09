import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import { Modal, FormField, Input, Textarea } from '@/ui'
import { slugify } from '@/lib/slugify'
import { ERA_LABELS, EMULATOR_CATALOG_SLUGS } from '@/generated/constants'
import type { EmulatorCatalogSlug } from '@/generated/constants'
import { ERA_COLOR } from '@/types/era'
import type { components } from '@shared/types'
type LaunchProfile = components['schemas']['ProfileRead']


const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))
const EMULATOR_OPTIONS = EMULATOR_CATALOG_SLUGS.map((slug) => ({ value: slug, label: slug }))

interface NewProfileForm {
  name: string
  slug: string
  emulator_slug: EmulatorCatalogSlug | ''
  era: string
  notes: string
}

const EMPTY: NewProfileForm = { name: '', slug: '', emulator_slug: '', era: '', notes: '' }

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function Profiles() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: profiles = [], isLoading } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState<NewProfileForm>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof NewProfileForm, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function setField<K extends keyof NewProfileForm>(key: K, value: NewProfileForm[K]) {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'name') next.slug = slugify(value as string)
      return next
    })
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function validate() {
    const e: Partial<Record<keyof NewProfileForm, string>> = {}
    if (!form.name.trim()) e.name = 'Name is required.'
    if (!form.slug.trim()) e.slug = 'Slug is required.'
    if (!form.emulator_slug.trim()) e.emulator_slug = 'Emulator slug is required.'
    if (!form.era) e.era = 'Era is required.'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleCreate() {
    if (!validate()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await apiFetch('/api/v1/profiles', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name.trim(),
          slug: form.slug.trim(),
          emulator_slug: form.emulator_slug.trim(),
          era: form.era,
          notes: form.notes.trim() || null,
          enable_networking: false,
        }),
      })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      setCreateOpen(false)
      setForm(EMPTY)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  const SELECT_CLS = 'w-full rounded-lg border px-3 py-2 text-sm outline-none focus:border-[#ff8a5c]'

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Profiles">
        <button
          type="button"
          onClick={() => { setForm(EMPTY); setErrors({}); setSubmitError(null); setCreateOpen(true) }}
          className="ml-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-[120ms]"
          style={{
            fontFamily: 'var(--font-display)',
            background: 'var(--peach-500)',
            border: 'none',
            color: '#1d0a04',
            cursor: 'pointer',
          }}
        >
          + New profile
        </button>
      </TopBar>

      <div className="p-6">
        <div className="mb-3 flex items-baseline gap-2.5">
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, letterSpacing: '-0.01em', margin: 0, color: 'var(--fg-1)' }}>
            Saved profiles
          </h2>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-3)' }}>
            {profiles.length} configurations
          </span>
        </div>

        {isLoading ? (
          <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 14 }}>Loading…</div>
        ) : profiles.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center"
            style={{
              border: '1px dashed var(--border-strong)',
              color: 'var(--fg-3)',
              fontFamily: 'var(--font-display)',
              fontSize: 14,
              backgroundImage:
                'repeating-linear-gradient(0deg, transparent 0 11px, rgb(255 138 92 / 0.04) 11px 12px), repeating-linear-gradient(90deg, transparent 0 11px, rgb(255 138 92 / 0.04) 11px 12px)',
            }}
          >
            No launch profiles. Create one to start configuring emulator launches.
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
            {/* Column headers */}
            <div
              className="grid px-[18px] py-2.5"
              style={{
                gridTemplateColumns: '1.7fr 0.7fr 0.9fr 0.6fr 0.8fr 0.5fr',
                fontFamily: 'var(--font-mono)',
                fontWeight: 500,
                fontSize: 11,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'var(--fg-3)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <span>Profile</span>
              <span>Era</span>
              <span>Backend</span>
              <span>Launches</span>
              <span>Created</span>
              <span></span>
            </div>

            {profiles.map((p, i) => {
              const eraKey = p.era.toUpperCase()
              const eraColor = ERA_COLOR[eraKey] ?? 'var(--fg-3)'
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => navigate(`/profiles/${p.slug}`)}
                  className="grid w-full px-[18px] py-3.5 text-left transition-colors duration-[120ms]"
                  style={{
                    gridTemplateColumns: '1.7fr 0.7fr 0.9fr 0.6fr 0.8fr 0.5fr',
                    alignItems: 'center',
                    gap: 8,
                    borderBottom: i < profiles.length - 1 ? '1px solid var(--border)' : 'none',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'grid',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <div>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)', display: 'flex', alignItems: 'center', gap: 8 }}>
                      {p.name}
                      {p.is_bundled && (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 6px', borderRadius: 'var(--r-1)', border: '1px solid var(--border)', color: 'var(--fg-3)', background: 'var(--surface-2)' }}>
                          default
                        </span>
                      )}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
                      {p.slug}.toml
                    </div>
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
                        border: `1px solid ${eraColor}`,
                        color: eraColor,
                        display: 'inline-block',
                        textTransform: 'uppercase',
                      }}
                    >
                      {eraKey}
                    </span>
                  </div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    {p.emulator_slug}
                    {p.enable_networking && (
                      <span style={{ color: 'var(--warning)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>· net on</span>
                    )}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-2)' }}>
                    —
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                    {formatDate(p.created_at)}
                  </div>
                  <div style={{ textAlign: 'right', color: 'var(--fg-3)' }}>›</div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Create modal */}
      <Modal
        open={createOpen}
        title="New Profile"
        onClose={() => setCreateOpen(false)}
        busy={submitting}
        footer={
          <>
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              style={{ background: 'transparent', border: 0, color: 'var(--fg-2)', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, cursor: 'pointer', padding: '9px 14px' }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleCreate}
              disabled={submitting}
              style={{ background: 'var(--peach-500)', border: 'none', color: '#1d0a04', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer' }}
            >
              {submitting ? 'Creating…' : 'Create Profile'}
            </button>
          </>
        }
      >
        <FormField label="Name" htmlFor="np-name" required error={errors.name}>
          <Input id="np-name" value={form.name} onChange={(e) => setField('name', e.target.value)} placeholder="DOS 486 / SoundBlaster 16" hasError={!!errors.name} />
        </FormField>
        <FormField label="Slug" htmlFor="np-slug" required hint="Auto-filled from name" error={errors.slug}>
          <Input id="np-slug" value={form.slug} onChange={(e) => setField('slug', e.target.value)} placeholder="dos-486-sb16" hasError={!!errors.slug} />
        </FormField>
        <FormField label="Emulator" htmlFor="np-emu" required error={errors.emulator_slug}>
          <select
            id="np-emu"
            value={form.emulator_slug}
            onChange={(e) => setField('emulator_slug', e.target.value as EmulatorCatalogSlug | '')}
            className={SELECT_CLS}
            style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
          >
            <option value="">— Select emulator —</option>
            {EMULATOR_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </FormField>
        <FormField label="Era" htmlFor="np-era" required error={errors.era}>
          <select
            id="np-era"
            value={form.era}
            onChange={(e) => setField('era', e.target.value)}
            className={SELECT_CLS}
            style={{ background: 'var(--surface-1)', borderColor: 'var(--border)', color: 'var(--fg-1)' }}
          >
            <option value="">— Select era —</option>
            {ERA_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </FormField>
        <FormField label="Notes" htmlFor="np-notes">
          <Textarea id="np-notes" value={form.notes} onChange={(e) => setField('notes', e.target.value)} rows={2} placeholder="Any notes…" />
        </FormField>
        {submitError && <p role="alert" style={{ color: 'var(--error)', fontFamily: 'var(--font-display)', fontSize: 13, margin: 0 }}>❌ {submitError}</p>}
      </Modal>
    </div>
  )
}
