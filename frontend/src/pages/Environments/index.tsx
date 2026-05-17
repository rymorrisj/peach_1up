import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, PageHeader } from '@/ui'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { useConfirm } from '@/hooks/useConfirm'
import type { components } from '@shared/types'
import EnvironmentCard from './EnvironmentCard'
import EnvironmentModal, {
  type EnvironmentForm,
  EMPTY_ENV_FORM,
  ERA_TO_EMULATOR,
} from './EnvironmentModal'

type Platform = components['schemas']['PlatformRead']

type EnvModalState = null | { mode: 'create' } | { mode: 'edit'; platform: Platform }

function formFromPlatform(p: Platform): EnvironmentForm {
  const ext = p as Platform & { hardware_profile?: string; machine_override?: string }
  return {
    name: p.name,
    era: p.era as EnvironmentForm['era'],
    base_image_path: p.base_image_path ?? '',
    working_image_path: p.working_image_path ?? '',
    hardware_profile: (ext.hardware_profile ?? 'standard') as EnvironmentForm['hardware_profile'],
    machine_override: ext.machine_override ?? '',
    notes: p.notes ?? '',
  }
}

export default function Environments() {
  const queryClient = useQueryClient()
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm()

  const { data: platforms, isLoading } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const userPlatforms = (platforms ?? []).filter((p) => !p.is_system)

  const [modal, setModal] = useState<EnvModalState>(null)
  const [form, setForm] = useState<EnvironmentForm>(EMPTY_ENV_FORM)
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof EnvironmentForm, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [healthLoading, setHealthLoading] = useState<number | null>(null)
  const [healthCheckAllRunning, setHealthCheckAllRunning] = useState(false)

  function openCreate() {
    setForm(EMPTY_ENV_FORM)
    setFormErrors({})
    setSubmitError(null)
    setModal({ mode: 'create' })
  }

  function openEdit(platform: Platform) {
    setForm(formFromPlatform(platform))
    setFormErrors({})
    setSubmitError(null)
    setModal({ mode: 'edit', platform })
  }

  function closeModal() {
    setModal(null)
  }

  function setField<K extends keyof EnvironmentForm>(key: K, value: EnvironmentForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setFormErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function validate(): boolean {
    const errors: Partial<Record<keyof EnvironmentForm, string>> = {}
    if (!form.name.trim()) errors.name = 'Name is required.'
    if (!form.era) errors.era = 'Select an environment era.'
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleSubmit() {
    if (!validate()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const era = form.era!
      const body = {
        name: form.name.trim(),
        era,
        emulator_slug: ERA_TO_EMULATOR[era],
        base_image_path: form.base_image_path.trim() || null,
        working_image_path: form.working_image_path.trim() || null,
        hardware_profile: form.hardware_profile,
        machine_override: form.machine_override.trim() || null,
        notes: form.notes.trim() || null,
      }
      if (modal?.mode === 'create') {
        await apiFetch('/api/v1/platforms', { method: 'POST', body: JSON.stringify(body) })
      } else if (modal?.mode === 'edit') {
        await apiFetch(`/api/v1/platforms/${modal.platform.id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        })
      }
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
      closeModal()
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(platform: Platform) {
    const confirmed = await confirm({
      title: `Delete "${platform.name}"?`,
      consequence: 'This removes the environment registration. OS images on disk are not deleted.',
      destructive: true,
    })
    if (!confirmed) return
    try {
      const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(
        `/api/v1/platforms/${platform.id}/confirm-delete`,
        { method: 'POST' },
      )
      await apiFetch(
        `/api/v1/platforms/${platform.id}?confirmation_token=${encodeURIComponent(confirmation_token)}`,
        { method: 'DELETE' },
      )
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Delete failed.')
    }
  }

  async function handleHealthCheck(platform: Platform) {
    setHealthLoading(platform.id)
    try {
      await apiFetch(`/api/v1/platforms/${platform.id}/health`, { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
    } catch {
      // Status update reflected via query invalidation
    } finally {
      setHealthLoading(null)
    }
  }

  async function handleHealthCheckAll() {
    setHealthCheckAllRunning(true)
    try {
      await apiFetch('/api/v1/platforms/health-all', { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
    } catch {
      // Partial failures handled server-side; statuses updated via invalidation
    } finally {
      setHealthCheckAllRunning(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Environments"
        description="Manage PC environment registrations and OS disk images."
        action={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={handleHealthCheckAll}
              loading={healthCheckAllRunning}
              disabled={healthCheckAllRunning || isLoading}
            >
              Health Check All
            </Button>
            <Button onClick={openCreate}>+ Add Environment</Button>
          </div>
        }
      />

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading environments…" />
          <span aria-hidden="true">Loading environments…</span>
        </div>
      ) : userPlatforms.length === 0 ? (
        <EmptyState
          heading="No environments yet"
          subtext="Add an environment to register a PC OS image for launching."
          cta={{ label: 'Add Environment', onClick: openCreate }}
        />
      ) : (
        <div className="space-y-3">
          {userPlatforms.map((platform) => (
            <EnvironmentCard
              key={platform.id}
              platform={platform}
              healthLoading={healthLoading === platform.id}
              onEdit={openEdit}
              onDelete={handleDelete}
              onHealthCheck={handleHealthCheck}
            />
          ))}
        </div>
      )}

      <EnvironmentModal
        open={modal !== null}
        mode={modal?.mode ?? 'create'}
        form={form}
        formErrors={formErrors}
        submitError={submitError}
        submitting={submitting}
        onClose={closeModal}
        onSubmit={handleSubmit}
        onFieldChange={setField}
      />

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
