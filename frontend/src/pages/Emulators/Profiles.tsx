import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button } from '@/ui'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import { usePaginatedList } from '@/hooks/usePaginatedList'
import { slugify } from '@/lib/slugify'
import { ERA_LABELS, EMULATOR_CATALOG_SLUGS } from '@/generated/constants'
import { ProfilesList } from './components/ProfilesList'
import { ProfileForm } from './components/ProfileForm'
import type { EmulatorEntry, LaunchProfile, ProfileForm as ProfileFormData, ProfileModalState } from '@/types/profiles'

const ERA_OPTIONS = Object.entries(ERA_LABELS).map(([value, label]) => ({ value, label }))
const EMULATOR_OPTIONS = EMULATOR_CATALOG_SLUGS.map((slug) => ({ value: slug, label: slug }))

const EMPTY_PROFILE_FORM: ProfileFormData = {
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

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

// Cross-emulator, flat list; editing is modal-only, no /emulators/profiles/:slug route.
export default function Profiles() {
  const queryClient = useQueryClient()
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm()

  const {
    items: profiles,
    isLoading,
    page,
    pageCount,
    hasPrevPage,
    hasNextPage,
    prevPage,
    nextPage,
  } = usePaginatedList<LaunchProfile>({ path: '/api/v1/profiles' })

  function invalidateProfiles() {
    return queryClient.invalidateQueries({ queryKey: ['paginated-list', '/api/v1/profiles'] })
  }

  const { data: emulators = [] } = useQuery<EmulatorEntry[]>({
    queryKey: ['emulators'],
    queryFn: () => apiFetch<EmulatorEntry[]>('/api/v1/emulator-items'),
  })

  const [modal, setModal] = useState<ProfileModalState>(null)
  const [form, setForm] = useState<ProfileFormData>(EMPTY_PROFILE_FORM)
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof ProfileFormData, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function openCreate() {
    setForm(EMPTY_PROFILE_FORM)
    setFormErrors({})
    setSubmitError(null)
    setModal({ mode: 'create' })
  }

  function openEdit(profile: LaunchProfile) {
    const ext = profile as LaunchProfile & {
      launch_commands?: string[] | null
      container_enabled?: boolean | null
      enable_dgvoodoo2?: boolean
    }
    setForm({
      name: profile.name,
      slug: profile.slug,
      emulator_slug: profile.emulator_slug as ProfileFormData['emulator_slug'],
      era: profile.era,
      extra_args: profile.extra_args ?? '',
      enable_networking: profile.enable_networking,
      enable_dgvoodoo2: ext.enable_dgvoodoo2 ?? false,
      notes: profile.notes ?? '',
      launch_commands: ext.launch_commands ?? [],
      container_enabled: ext.container_enabled ?? null,
    })
    setFormErrors({})
    setSubmitError(null)
    setModal({ mode: 'edit', profile })
  }

  function closeModal() {
    setModal(null)
  }

  function setField<K extends keyof ProfileFormData>(key: K, value: ProfileFormData[K]) {
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
    const errors: Partial<Record<keyof ProfileFormData, string>> = {}
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
        launch_commands: form.launch_commands,
        container_enabled: form.container_enabled,
      }
      if (form.extra_args.trim()) body.extra_args = form.extra_args.trim()
      if (form.notes.trim()) body.notes = form.notes.trim()

      if (modal?.mode === 'create') {
        await apiFetch('/api/v1/profiles', { method: 'POST', body: JSON.stringify(body) })
      } else if (modal?.mode === 'edit') {
        await apiFetch(`/api/v1/profiles/${modal.profile.slug}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        })
      }
      await invalidateProfiles()
      closeModal()
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(profile: LaunchProfile) {
    const confirmed = await confirm({
      title: `Delete "${profile.name}"?`,
      consequence:
        'This launch profile will be permanently removed. Any library items using it will lose their profile assignment.',
      destructive: true,
    })
    if (!confirmed) return
    try {
      await apiFetch(`/api/v1/profiles/${profile.slug}`, { method: 'DELETE' })
      await invalidateProfiles()
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Delete failed.')
    }
  }

  const eraLabel = (era: string) => ERA_OPTIONS.find((e) => e.value === era)?.label ?? era

  return (
    <div className="p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Emulator configuration presets. Assign a profile to each library item to enable launch.
        </p>
        <Button size="sm" onClick={openCreate} className="shrink-0">
          + Add Profile
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading launch profiles…" />
          <span aria-hidden="true">Loading launch profiles…</span>
        </div>
      ) : profiles.length === 0 ? (
        <EmptyState
          heading="No launch profiles"
          subtext="Launch profiles define the emulator configuration used when launching media. Default profiles are seeded at first run."
          cta={{ label: 'Add Profile', onClick: openCreate }}
        />
      ) : (
        <>
          <ProfilesList
            profiles={profiles}
            eraLabel={eraLabel}
            formatDate={formatDate}
            onEdit={openEdit}
            onDelete={handleDelete}
          />
          {pageCount > 1 && (
            <div className="mt-4 flex items-center justify-between gap-4">
              <Button variant="secondary" size="sm" onClick={prevPage} disabled={!hasPrevPage}>
                Previous
              </Button>
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                Page {page} of {pageCount}
              </span>
              <Button variant="secondary" size="sm" onClick={nextPage} disabled={!hasNextPage}>
                Next
              </Button>
            </div>
          )}
        </>
      )}

      <ProfileForm
        modal={modal}
        form={form}
        formErrors={formErrors}
        submitError={submitError}
        submitting={submitting}
        emulators={emulators}
        eraOptions={ERA_OPTIONS}
        emulatorOptions={EMULATOR_OPTIONS}
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
  )
}
