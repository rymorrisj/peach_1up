import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Modal, PageHeader, Textarea } from '@/ui'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import type { UserProfile, Platform } from '@/types'

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
  pin: string
  platform_slug: string
  era: string
  custom_flags: string
  rom_pack_path: string
  custom_script: string
  notes: string
}

const EMPTY_FORM: ProfileForm = {
  name: '',
  pin: '',
  platform_slug: '',
  era: '',
  custom_flags: '',
  rom_pack_path: '',
  custom_script: '',
  notes: '',
}

type ModalState = null | { mode: 'create' } | { mode: 'edit'; profile: UserProfile }

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function Profiles() {
  const queryClient = useQueryClient()
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm()

  const { data: profiles, isLoading } = useQuery<UserProfile[]>({
    queryKey: ['user-profiles'],
    queryFn: () => apiFetch<UserProfile[]>('/api/v1/profiles/users'),
  })

  const { data: platforms = [] } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const systemPlatforms = platforms.filter((p) => p.is_system)

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

  function openEdit(profile: UserProfile) {
    setForm({
      name: profile.name,
      pin: '',
      platform_slug: profile.platform_slug ?? '',
      era: profile.era ?? '',
      custom_flags: profile.custom_flags ?? '',
      rom_pack_path: profile.rom_pack_path ?? '',
      custom_script: profile.custom_script ?? '',
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
    setForm((prev) => ({ ...prev, [key]: value }))
    setFormErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function validate(): boolean {
    const errors: Partial<Record<keyof ProfileForm, string>> = {}
    if (!form.name.trim()) errors.name = 'Name is required.'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleSubmit() {
    if (!validate()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const body: Record<string, string | null> = { name: form.name.trim() }
      if (form.pin.trim()) body.pin = form.pin.trim()
      if (form.platform_slug) body.platform_slug = form.platform_slug
      if (form.era) body.era = form.era
      if (form.custom_flags.trim()) body.custom_flags = form.custom_flags.trim()
      if (form.rom_pack_path.trim()) body.rom_pack_path = form.rom_pack_path.trim()
      if (form.custom_script.trim()) body.custom_script = form.custom_script.trim()
      if (form.notes.trim()) body.notes = form.notes.trim()

      if (modal?.mode === 'create') {
        await apiFetch('/api/v1/profiles/users', { method: 'POST', body: JSON.stringify(body) })
      } else if (modal?.mode === 'edit') {
        await apiFetch(`/api/v1/profiles/users/${modal.profile.id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        })
      }
      await queryClient.invalidateQueries({ queryKey: ['user-profiles'] })
      closeModal()
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Something went wrong.'
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(profile: UserProfile) {
    const confirmed = await confirm({
      title: `Delete "${profile.name}"?`,
      consequence: 'This profile will be permanently removed.',
      destructive: true,
    })
    if (!confirmed) return

    try {
      await apiFetch(`/api/v1/profiles/users/${profile.id}`, { method: 'DELETE' })
      await queryClient.invalidateQueries({ queryKey: ['user-profiles'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Delete failed.'
      alert(msg)
    }
  }

  const modalTitle = modal?.mode === 'create' ? 'Add Profile' : 'Edit Profile'

  return (
    <>
      <PageHeader
        title="Profiles"
        description="Manage who can use this library. Each profile can have its own PIN and launch preferences."
        action={<Button onClick={openCreate}>+ Add Profile</Button>}
      />

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading profiles…" />
          <span aria-hidden="true">Loading profiles…</span>
        </div>
      ) : !profiles || profiles.length === 0 ? (
        <EmptyState
          heading="No profiles yet"
          subtext="Add a profile to manage who can access this library."
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
                    {profile.is_owner && (
                      <span className="rounded-full bg-peach/15 px-2 py-0.5 text-xs font-medium text-peach">
                        Owner
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-neutral-400 dark:text-neutral-500">
                    Created {formatDate(profile.created_at)}
                    {profile.last_active_at && (
                      <> · Last active {formatDate(profile.last_active_at)}</>
                    )}
                    {profile.era && (
                      <> · Era: {ERA_OPTIONS.find((e) => e.value === profile.era)?.label ?? profile.era}</>
                    )}
                    {profile.platform_slug && <> · Platform: {profile.platform_slug}</>}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button variant="secondary" size="sm" onClick={() => openEdit(profile)}>
                    Edit
                  </Button>
                  {!profile.is_owner && (
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
        <FormField label="Name" htmlFor="prof-name" required error={formErrors.name}>
          <Input
            id="prof-name"
            value={form.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="Profile name"
            hasError={!!formErrors.name}
          />
        </FormField>

        <FormField
          label={modal?.mode === 'create' ? 'PIN (optional)' : 'New PIN (optional)'}
          htmlFor="prof-pin"
          hint={
            modal?.mode === 'edit'
              ? 'Leave blank to keep the existing PIN'
              : 'Leave blank for a PIN-free profile'
          }
        >
          <Input
            id="prof-pin"
            type="password"
            value={form.pin}
            onChange={(e) => setField('pin', e.target.value)}
            placeholder="••••"
            autoComplete="new-password"
          />
        </FormField>

        <FormField label="Preferred Platform" htmlFor="prof-platform" hint="Emulator platform this profile prefers">
          <select
            id="prof-platform"
            value={form.platform_slug}
            onChange={(e) => setField('platform_slug', e.target.value)}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
          >
            <option value="">— No preference —</option>
            {systemPlatforms.map((p) => (
              <option key={p.id} value={p.slug ?? p.emulator_slug}>
                {p.name}
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Preferred Era" htmlFor="prof-era" hint="Default era when launching media">
          <select
            id="prof-era"
            value={form.era}
            onChange={(e) => setField('era', e.target.value)}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
          >
            <option value="">— No preference —</option>
            {ERA_OPTIONS.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField label="Custom Flags" htmlFor="prof-flags" hint="Additional emulator command-line flags">
          <Input
            id="prof-flags"
            value={form.custom_flags}
            onChange={(e) => setField('custom_flags', e.target.value)}
            placeholder="-fullscreen -noaudio"
          />
        </FormField>

        <FormField label="ROM Pack Path" htmlFor="prof-rom" hint="Path to ROM pack if required by platform">
          <Input
            id="prof-rom"
            value={form.rom_pack_path}
            onChange={(e) => setField('rom_pack_path', e.target.value)}
            placeholder="C:/roms/86box-roms"
          />
        </FormField>

        <FormField label="Pre-launch Script" htmlFor="prof-script" hint="Command or script to run before launch">
          <Textarea
            id="prof-script"
            value={form.custom_script}
            onChange={(e) => setField('custom_script', e.target.value)}
            placeholder="echo 'Starting emulator…'"
            rows={2}
          />
        </FormField>

        <FormField label="Notes" htmlFor="prof-notes">
          <Textarea
            id="prof-notes"
            value={form.notes}
            onChange={(e) => setField('notes', e.target.value)}
            placeholder="Any notes about this profile…"
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
