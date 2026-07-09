import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import TopBar from '@/components/layout/TopBar'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import { slugify } from '@/lib/slugify'
import { ERA_LABELS } from '@/generated/constants'
import { ProfileList } from './components/ProfileList'
import { ProfileFormModal } from './components/ProfileFormModal'
import type { EmulatorEntry, LaunchProfile, ProfileForm, ProfileModalState } from '@/types/profiles'

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))

const EMPTY_FORM: ProfileForm = {
  name: '',
  slug: '',
  emulator_slug: '',
  era: '',
  extra_args: '',
  enable_networking: false,
  enable_dgvoodoo2: false,
  notes: '',
  launch_commands: [],
  container_enabled: null,
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function LaunchProfiles() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm()

  const { data: profiles, isLoading } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const { data: emulators = [] } = useQuery<EmulatorEntry[]>({
    queryKey: ['emulators'],
    queryFn: () => apiFetch<EmulatorEntry[]>('/api/v1/emulators'),
  })

  const [modal, setModal] = useState<ProfileModalState>(null)
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
    const ext = profile as LaunchProfile & {
      container_enabled?: boolean | null
      enable_dgvoodoo2?: boolean
    }
    setForm({
      name: profile.name,
      slug: profile.slug,
      emulator_slug: profile.emulator_slug,
      era: profile.era,
      extra_args: profile.extra_args ?? '',
      enable_networking: profile.enable_networking,
      enable_dgvoodoo2: ext.enable_dgvoodoo2 ?? false,
      notes: profile.notes ?? '',
      launch_commands: profile.launch_commands ?? [],
      container_enabled: ext.container_enabled ?? null,
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
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        slug: form.slug.trim(),
        emulator_slug: form.emulator_slug.trim(),
        era: form.era,
        enable_networking: form.enable_networking,
        enable_dgvoodoo2: form.enable_dgvoodoo2,
        container_enabled: form.container_enabled,
      }
      if (form.extra_args.trim()) body.extra_args = form.extra_args.trim()
      if (form.notes.trim()) body.notes = form.notes.trim()
      // Always send launch_commands (including []) so clearing them persists;
      // omitting the field left a stale list on the profile (exclude_unset).
      body.launch_commands = form.launch_commands

      if (modal?.mode === 'create') {
        await apiFetch('/api/v1/profiles', { method: 'POST', body: JSON.stringify(body) })
        await queryClient.invalidateQueries({ queryKey: ['profiles'] })
        closeModal()
      } else if (modal?.mode === 'edit') {
        const updated = await apiFetch<LaunchProfile>(`/api/v1/profiles/${modal.profile.slug}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        })
        await queryClient.invalidateQueries({ queryKey: ['profiles'] })
        closeModal()
        navigate(`/profiles/${updated.slug}`)
      }
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
      await apiFetch(`/api/v1/profiles/${profile.slug}`, { method: 'DELETE' })
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Delete failed.'
      alert(msg)
    }
  }

  const eraLabel = (era: string) =>
    ERA_OPTIONS.find((e) => e.value === era)?.label ?? era

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Profiles">
        <Button onClick={openCreate}>+ Add Profile</Button>
      </TopBar>

      <div className="p-6">
        <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
          Emulator configuration presets. Assign a profile to each library item to enable launch.
        </p>

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
        <ProfileList
          profiles={profiles}
          eraLabel={eraLabel}
          formatDate={formatDate}
          onSelect={(profile) => navigate(`/profiles/${profile.slug}`)}
          onEdit={openEdit}
          onDelete={handleDelete}
        />
      )}

      <ProfileFormModal
        modal={modal}
        form={form}
        formErrors={formErrors}
        submitError={submitError}
        submitting={submitting}
        emulators={emulators}
        eraOptions={ERA_OPTIONS}
        setField={setField}
        onSubmit={handleSubmit}
        onClose={closeModal}
      />

      <ConfirmModal
        open={isOpen}
        title={options?.title ?? ''}
        consequence={options?.consequence ?? ''}
        destructive={options?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />

      </div>
    </div>
  )
}
