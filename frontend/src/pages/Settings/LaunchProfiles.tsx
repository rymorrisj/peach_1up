import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Modal, PageHeader, Textarea } from '@/ui'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import type { LaunchProfile } from '@/types'

const ERA_OPTIONS = [
  { value: 'dos', label: 'DOS' },
  { value: 'win31', label: 'Windows 3.1' },
  { value: 'win95', label: 'Windows 95' },
  { value: 'win98', label: 'Windows 98' },
  { value: 'winxp', label: 'Windows XP' },
  { value: 'ps1', label: 'PlayStation 1' },
  { value: 'ps2', label: 'PlayStation 2' },
  { value: 'xbox', label: 'Original Xbox' },
  { value: 'nes', label: 'NES' },
  { value: 'n64', label: 'Nintendo 64' },
]

interface ProfileForm {
  name: string
  slug: string
  emulator_slug: string
  era: string
  extra_args: string
  enable_networking: boolean
  notes: string
}

const EMPTY_FORM: ProfileForm = {
  name: '',
  slug: '',
  emulator_slug: '',
  era: '',
  extra_args: '',
  enable_networking: false,
  notes: '',
}

type ModalState = null | { mode: 'create' } | { mode: 'edit'; profile: LaunchProfile }

function slugify(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function LaunchProfiles() {
  const queryClient = useQueryClient()
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm()

  const { data: profiles, isLoading } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const [modal, setModal] = useState<ModalState>(null)
  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM)
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof ProfileForm, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function openCreate() {
    setForm(EMPTY_FORM)
    setFormErrors({})
    setSubmitError(null)
    setModal({ mode: 'create' })
  }

  function openEdit(profile: LaunchProfile) {
    setForm({
      name: profile.name,
      slug: profile.slug,
      emulator_slug: profile.emulator_slug,
      era: profile.era,
      extra_args: profile.extra_args ?? '',
      enable_networking: profile.enable_networking,
      notes: profile.notes ?? '',
    })
    setFormErrors({})
    setSubmitError(null)
    setModal({ mode: 'edit', profile })
  }

  function closeModal() {
    setModal(null)
  }

  function setField<K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'name' && modal?.mode === 'create') {
        next.slug = slugify(value as string)
      }
      return next
    })
    setFormErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function validate(): boolean {
    const errors: Partial<Record<keyof ProfileForm, string>> = {}
    if (!form.name.trim()) errors.name = 'Name is required.'
    if (!form.slug.trim()) errors.slug = 'Slug is required.'
    if (!form.emulator_slug.trim()) errors.emulator_slug = 'Emulator slug is required.'
    if (!form.era) errors.era = 'Era is required.'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleSubmit() {
    if (!validate()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const body: Record<string, string | boolean | null> = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        emulator_slug: form.emulator_slug.trim(),
        era: form.era,
        enable_networking: form.enable_networking,
      }
      if (form.extra_args.trim()) body.extra_args = form.extra_args.trim()
      if (form.notes.trim()) body.notes = form.notes.trim()

      if (modal?.mode === 'create') {
        await apiFetch('/api/v1/profiles', { method: 'POST', body: JSON.stringify(body) })
      } else if (modal?.mode === 'edit') {
        await apiFetch(`/api/v1/profiles/${modal.profile.id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        })
      }
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      closeModal()
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Something went wrong.'
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(profile: LaunchProfile) {
    const confirmed = await confirm({
      title: `Delete "${profile.name}"?`,
      consequence: 'This launch profile will be permanently removed. Any library items using it will lose their profile assignment.',
      destructive: true,
    })
    if (!confirmed) return

    try {
      await apiFetch(`/api/v1/profiles/${profile.id}`, { method: 'DELETE' })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Delete failed.'
      alert(msg)
    }
  }

  const eraLabel = (era: string) =>
    ERA_OPTIONS.find((e) => e.value === era)?.label ?? era

  const modalTitle = modal?.mode === 'create' ? 'Add Launch Profile' : 'Edit Launch Profile'

  return (
    <>
      <PageHeader
        title="Profiles"
        description="Emulator configuration presets. Assign a profile to each library item to enable launch."
        action={<Button onClick={openCreate}>+ Add Profile</Button>}
      />

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading launch profiles…" />
          <span aria-hidden="true">Loading launch profiles…</span>
        </div>
      ) : !profiles || profiles.length === 0 ? (
        <EmptyState
          heading="No launch profiles"
          subtext="Launch profiles define the emulator configuration used when launching media. Default profiles are seeded at first run."
          cta={{ label: 'Add Profile', onClick: openCreate }}
        />
      ) : (
        <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {profiles.map((profile) => (
            <li key={profile.id} className="py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-neutral-900 dark:text-neutral-100">
                      {profile.name}
                    </span>
                    {profile.is_bundled && (
                      <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-500 dark:bg-surface-700 dark:text-neutral-400">
                        default
                      </span>
                    )}
                    {profile.enable_networking && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                        networking on
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-neutral-400 dark:text-neutral-500">
                    {eraLabel(profile.era)} · {profile.emulator_slug}
                    {' · '}Created {formatDate(profile.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button variant="secondary" size="sm" onClick={() => openEdit(profile)}>
                    Edit
                  </Button>
                  {!profile.is_bundled && (
                    <Button variant="destructive" size="sm" onClick={() => handleDelete(profile)}>
                      Delete
                    </Button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={modal !== null}
        title={modalTitle}
        onClose={closeModal}
        footer={
          <>
            <Button variant="ghost" onClick={closeModal} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} loading={submitting}>
              {modal?.mode === 'create' ? 'Add Profile' : 'Save Changes'}
            </Button>
          </>
        }
      >
        <FormField label="Name" htmlFor="lp-name" required error={formErrors.name}>
          <Input
            id="lp-name"
            value={form.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="DOS 486DX2 / SoundBlaster 16"
            hasError={!!formErrors.name}
          />
        </FormField>

        <FormField
          label="Slug"
          htmlFor="lp-slug"
          required
          hint="Unique identifier — auto-filled from name"
          error={formErrors.slug}
        >
          <Input
            id="lp-slug"
            value={form.slug}
            onChange={(e) => setField('slug', e.target.value)}
            placeholder="dos-486dx2-sb16"
            hasError={!!formErrors.slug}
          />
        </FormField>

        <FormField
          label="Emulator Slug"
          htmlFor="lp-emulator"
          required
          hint="e.g. dosbox, box86, virtualbox, duckstation"
          error={formErrors.emulator_slug}
        >
          <Input
            id="lp-emulator"
            value={form.emulator_slug}
            onChange={(e) => setField('emulator_slug', e.target.value)}
            placeholder="dosbox"
            hasError={!!formErrors.emulator_slug}
          />
        </FormField>

        <FormField label="Era" htmlFor="lp-era" required error={formErrors.era}>
          <select
            id="lp-era"
            value={form.era}
            onChange={(e) => setField('era', e.target.value)}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
          >
            <option value="">— Select era —</option>
            {ERA_OPTIONS.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Extra Arguments" htmlFor="lp-args" hint="Additional command-line flags passed to the emulator">
          <Input
            id="lp-args"
            value={form.extra_args}
            onChange={(e) => setField('extra_args', e.target.value)}
            placeholder="-fullscreen"
          />
        </FormField>

        <FormField
          label="Enable networking"
          htmlFor="lp-networking"
          hint="When off, the emulator's network adapter is disabled. Enable only if this software requires a network connection."
        >
          <div className="mt-1 flex items-center gap-3">
            <button
              id="lp-networking"
              type="button"
              role="switch"
              aria-checked={form.enable_networking}
              onClick={() => setField('enable_networking', !form.enable_networking)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#ff8a5c] focus:ring-offset-2 ${
                form.enable_networking
                  ? 'bg-[#ff8a5c]'
                  : 'bg-neutral-300 dark:bg-neutral-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  form.enable_networking ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className="text-sm text-neutral-600 dark:text-neutral-300">
              {form.enable_networking ? 'On' : 'Off (default)'}
            </span>
          </div>
        </FormField>

        <FormField label="Notes" htmlFor="lp-notes">
          <Textarea
            id="lp-notes"
            value={form.notes}
            onChange={(e) => setField('notes', e.target.value)}
            placeholder="Any notes about this launch profile…"
            rows={2}
          />
        </FormField>

        {submitError && (
          <p role="alert" className="text-sm text-error">
            ❌ {submitError}
          </p>
        )}
      </Modal>

      <ConfirmModal
        open={isOpen}
        title={options?.title ?? ''}
        consequence={options?.consequence ?? ''}
        destructive={options?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  )
}
