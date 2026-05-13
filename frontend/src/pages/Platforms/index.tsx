import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { Button, FormField, Input, Modal, PageHeader, StatusBadge, Textarea } from '@/ui'
import EraSelector, { type EraValue } from '@/components/common/EraSelector'
import ConfirmModal from '@/components/common/ConfirmModal'
import EmptyState from '@/components/common/EmptyState'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'
import { useConfirm } from '@/hooks/useConfirm'
import { ERA_LABELS } from '@/generated/constants'
import type { Platform } from '@/types'

const ERA_TO_EMULATOR: Record<string, string> = {
  dos: 'dosbox-x',
  win31: 'dosbox-x',
  win95: 'virtualbox',
  win98: 'virtualbox',
  winxp: 'virtualbox',
  ps1: 'duckstation',
  ps2: 'pcsx2',
  xbox: 'xemu',
  nes: 'mesen',
  n64: 'project64',
}

const EMULATOR_LABELS: Record<string, string> = {
  'dosbox-x': 'DOSBox-X',
  '86box': '86Box',
  virtualbox: 'VirtualBox',
  duckstation: 'DuckStation',
  pcsx2: 'PCSX2',
  xemu: 'xemu',
  mesen: 'Mesen',
  project64: 'Project64',
}

interface PlatformForm {
  name: string
  era: EraValue | null
  base_image_path: string
  working_image_path: string
  notes: string
}

const EMPTY_FORM: PlatformForm = {
  name: '',
  era: null,
  base_image_path: '',
  working_image_path: '',
  notes: '',
}

type ModalState = null | { mode: 'create' } | { mode: 'edit'; platform: Platform }

function formFromPlatform(p: Platform): PlatformForm {
  return {
    name: p.name,
    era: p.era as EraValue,
    base_image_path: p.base_image_path ?? '',
    working_image_path: p.working_image_path ?? '',
    notes: p.notes ?? '',
  }
}

export default function Platforms() {
  const queryClient = useQueryClient()
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm()

  const { data: platforms, isLoading } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/platforms'),
  })

  const [modal, setModal] = useState<ModalState>(null)
  const [form, setForm] = useState<PlatformForm>(EMPTY_FORM)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof PlatformForm, string>>>({})
  const [healthLoading, setHealthLoading] = useState<number | null>(null)

  function openCreate() {
    setForm(EMPTY_FORM)
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

  function setField<K extends keyof PlatformForm>(key: K, value: PlatformForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setFormErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function validate(): boolean {
    const errors: Partial<Record<keyof PlatformForm, string>> = {}
    if (!form.name.trim()) errors.name = 'Name is required.'
    if (!form.era) errors.era = 'Select a platform era.'
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
      const msg = err instanceof ApiError ? err.detail : 'Something went wrong.'
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(platform: Platform) {
    const confirmed = await confirm({
      title: `Delete "${platform.name}"?`,
      consequence:
        'This removes the platform registration. OS images on disk are not deleted.',
      destructive: true,
    })
    if (!confirmed) return

    try {
      const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(
        `/api/v1/platforms/${platform.id}/confirm-delete`,
        { method: 'POST' },
      )
      await apiFetch(`/api/v1/platforms/${platform.id}?confirmation_token=${encodeURIComponent(confirmation_token)}`, {
        method: 'DELETE',
      })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Delete failed.'
      alert(msg)
    }
  }

  async function handleHealthCheck(platform: Platform) {
    setHealthLoading(platform.id)
    try {
      await apiFetch(`/api/v1/platforms/${platform.id}/health`, { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['platforms'] })
    } catch {
      // Health check errors are surfaced via the updated status badge
    } finally {
      setHealthLoading(null)
    }
  }

  const modalTitle = modal?.mode === 'create' ? 'Add Platform' : 'Edit Platform'
  const emulatorLabel = form.era
    ? (EMULATOR_LABELS[ERA_TO_EMULATOR[form.era]] ?? ERA_TO_EMULATOR[form.era])
    : null

  return (
    <>
      <PageHeader
        title="Platforms"
        description="Registered OS platform images. Each platform is a base image paired with a working copy."
        action={
          <Button onClick={openCreate}>+ Add Platform</Button>
        }
      />

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading platforms…" />
          <span aria-hidden="true">Loading platforms…</span>
        </div>
      ) : !platforms || platforms.length === 0 ? (
        <EmptyState
          heading="No platforms registered"
          subtext="Add a base OS image to get started. Each platform supports Win 95, 98, XP, and more."
          cta={{ label: 'Add Platform', onClick: openCreate }}
        />
      ) : (
        <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {platforms.map((p) => (
            <li key={p.id} className="py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-neutral-900 dark:text-neutral-100">{p.name}</span>
                    <StatusBadge status={p.status} />
                  </div>
                  <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
                    {ERA_LABELS[p.era] ?? p.era} ·{' '}
                    {EMULATOR_LABELS[p.emulator_slug] ?? p.emulator_slug}
                  </p>
                  {p.last_health_check && (
                    <p className="mt-0.5 text-xs text-neutral-400 dark:text-neutral-500">
                      Last checked {new Date(p.last_health_check).toLocaleString()}
                    </p>
                  )}
                  {p.notes && (
                    <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{p.notes}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleHealthCheck(p)}
                    loading={healthLoading === p.id}
                    disabled={healthLoading === p.id}
                  >
                    Health Check
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => openEdit(p)}>
                    Edit
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => handleDelete(p)}>
                    Delete
                  </Button>
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
              {modal?.mode === 'create' ? 'Add Platform' : 'Save Changes'}
            </Button>
          </>
        }
      >
        <FormField label="Name" htmlFor="plat-name" required error={formErrors.name}>
          <Input
            id="plat-name"
            value={form.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="My Windows 98 Setup"
            hasError={!!formErrors.name}
          />
        </FormField>

        <FormField label="Platform Era" required error={formErrors.era}>
          <div className="mt-1">
            <EraSelector
              value={form.era}
              onChange={(era) => setField('era', era)}
              disabled={submitting}
            />
          </div>
        </FormField>

        {emulatorLabel && (
          <div>
            <span className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Emulator (auto-selected)
            </span>
            <span className="mt-1 block text-sm text-neutral-500 dark:text-neutral-400">
              {emulatorLabel}
            </span>
          </div>
        )}

        <FormField
          label="Base Image Path"
          htmlFor="plat-base"
          hint="Full path to the locked base image file (never modified)"
        >
          <PathInput
            id="plat-base"
            mode="file"
            accept=".img,.iso,.vhd,.cue,.chd,.xiso"
            value={form.base_image_path}
            onChange={(v) => setField('base_image_path', v)}
            placeholder="/path/to/images/os/win98/base.img"
            className="mt-1"
          />
        </FormField>

        <FormField
          label="Working Image Path"
          htmlFor="plat-working"
          hint="Full path to the working copy used for all launches"
        >
          <PathInput
            id="plat-working"
            mode="file"
            accept=".img,.iso,.vhd,.cue,.chd,.xiso"
            value={form.working_image_path}
            onChange={(v) => setField('working_image_path', v)}
            placeholder="/path/to/images/os/win98/working.img"
            className="mt-1"
          />
        </FormField>

        <FormField label="Notes" htmlFor="plat-notes">
          <Textarea
            id="plat-notes"
            value={form.notes}
            onChange={(e) => setField('notes', e.target.value)}
            placeholder="Optional notes about this platform"
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
