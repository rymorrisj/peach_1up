import { Button, FormField, Input, Modal, Textarea, Select } from '@/ui'
import { DGVOODOO2_SUPPORTED_ERAS } from '@/generated/constants'
import type { EmulatorEntry, ProfileForm, ProfileModalState } from '@/types/profiles'

interface ProfileFormModalProps {
  modal: ProfileModalState
  form: ProfileForm
  formErrors: Partial<Record<keyof ProfileForm, string>>
  submitError: string | null
  submitting: boolean
  emulators: EmulatorEntry[]
  eraOptions: Array<{ value: string; label: string }>
  setField: <K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) => void
  onSubmit: () => void
  onClose: () => void
}

export function ProfileFormModal({
  modal, form, formErrors, submitError, submitting, emulators, eraOptions, setField, onSubmit, onClose,
}: ProfileFormModalProps) {
  const modalTitle = modal?.mode === 'create' ? 'Add Launch Profile' : 'Edit Launch Profile'

  return (
    <Modal
      open={modal !== null}
      title={modalTitle}
      onClose={onClose}
      busy={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onSubmit} loading={submitting}>
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
        label="Emulator"
        htmlFor="lp-emulator"
        required
        error={formErrors.emulator_slug}
      >
        <Select
          id="lp-emulator"
          value={form.emulator_slug}
          onValueChange={(v) => setField('emulator_slug', v)}
          placeholder="— Select emulator —"
          hasError={!!formErrors.emulator_slug}
          options={emulators.map((e) => ({ value: e.slug, label: e.slug }))}
        />
      </FormField>

      <FormField label="Era" htmlFor="lp-era" required error={formErrors.era}>
        <Select
          id="lp-era"
          value={form.era}
          onValueChange={(v) => setField('era', v)}
          placeholder="— Select era —"
          hasError={!!formErrors.era}
          options={eraOptions}
        />
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
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 ${
              form.enable_networking
                ? 'bg-accent'
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

      {DGVOODOO2_SUPPORTED_ERAS.includes(form.era) && (
        <FormField
          label="dgVoodoo2 (3D compatibility)"
          htmlFor="lp-dgvoodoo2"
          hint="Injects dgVoodoo2 shims for games requiring legacy Direct3D support. Place DLLs in library/system/tools/dgvoodoo2/."
        >
          <div className="mt-1 flex items-center gap-3">
            <button
              id="lp-dgvoodoo2"
              type="button"
              role="switch"
              aria-checked={form.enable_dgvoodoo2}
              onClick={() => setField('enable_dgvoodoo2', !form.enable_dgvoodoo2)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 ${
                form.enable_dgvoodoo2
                  ? 'bg-accent'
                  : 'bg-neutral-300 dark:bg-neutral-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  form.enable_dgvoodoo2 ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className="text-sm text-neutral-600 dark:text-neutral-300">
              {form.enable_dgvoodoo2 ? 'On' : 'Off (default)'}
            </span>
          </div>
        </FormField>
      )}

      <FormField label="Notes" htmlFor="lp-notes">
        <Textarea
          id="lp-notes"
          value={form.notes}
          onChange={(e) => setField('notes', e.target.value)}
          placeholder="Any notes about this launch profile…"
          rows={2}
        />
      </FormField>

      {emulators.find((e) => e.slug === form.emulator_slug)?.container_enabled && (
        <FormField
          label="AppContainer"
          htmlFor="lp-container"
          hint="Override the emulator's default AppContainer setting for this profile"
        >
          <Select
            id="lp-container"
            value={form.container_enabled === null ? 'default' : form.container_enabled ? 'true' : 'false'}
            onValueChange={(v) => setField('container_enabled', v === 'default' ? null : v === 'true')}
            options={[
              { value: 'default', label: 'Default (use emulator setting)' },
              { value: 'true', label: 'Enabled' },
              { value: 'false', label: 'Disabled' },
            ]}
          />
        </FormField>
      )}

      {submitError && (
        <p role="alert" className="text-sm text-error">
          ❌ {submitError}
        </p>
      )}
    </Modal>
  )
}
