import { Button, FormField, Input, Modal, Textarea } from '@/ui'
import PathInput from '@/components/common/PathInput'
import FileUpload from '@/components/common/FileUpload'

type PCEra = 'dos' | 'win31' | 'win95' | 'win98' | 'winxp'

const PC_ERAS: { value: PCEra; label: string }[] = [
  { value: 'dos', label: 'DOS' },
  { value: 'win31', label: 'Windows 3.1' },
  { value: 'win95', label: 'Windows 95' },
  { value: 'win98', label: 'Windows 98' },
  { value: 'winxp', label: 'Windows XP' },
]

const ERA_TO_EMULATOR: Record<PCEra, string> = {
  dos: 'dosbox-x',
  win31: 'dosbox-x',
  win95: 'virtualbox',
  win98: 'virtualbox',
  winxp: 'virtualbox',
}

const EMULATOR_LABELS: Record<string, string> = {
  'dosbox-x': 'DOSBox-X',
  virtualbox: 'VirtualBox',
}

export interface EnvironmentForm {
  name: string
  era: PCEra | null
  base_image_path: string
  working_image_path: string
  notes: string
}

export const EMPTY_ENV_FORM: EnvironmentForm = {
  name: '',
  era: null,
  base_image_path: '',
  working_image_path: '',
  notes: '',
}

export { ERA_TO_EMULATOR }

interface EnvironmentModalProps {
  open: boolean
  mode: 'create' | 'edit'
  form: EnvironmentForm
  formErrors: Partial<Record<keyof EnvironmentForm, string>>
  submitError: string | null
  submitting: boolean
  onClose: () => void
  onSubmit: () => void
  onFieldChange: <K extends keyof EnvironmentForm>(key: K, value: EnvironmentForm[K]) => void
}

export default function EnvironmentModal({
  open,
  mode,
  form,
  formErrors,
  submitError,
  submitting,
  onClose,
  onSubmit,
  onFieldChange,
}: EnvironmentModalProps) {
  const emulatorLabel = form.era ? (EMULATOR_LABELS[ERA_TO_EMULATOR[form.era]] ?? null) : null

  return (
    <Modal
      open={open}
      title={mode === 'create' ? 'Add Environment' : 'Edit Environment'}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onSubmit} loading={submitting}>
            {mode === 'create' ? 'Add Environment' : 'Save Changes'}
          </Button>
        </>
      }
    >
      <FormField label="Name" htmlFor="env-name" required error={formErrors.name}>
        <Input
          id="env-name"
          value={form.name}
          onChange={(e) => onFieldChange('name', e.target.value)}
          placeholder="My Windows 98 Setup"
          hasError={!!formErrors.name}
        />
      </FormField>

      <FormField label="Era" required error={formErrors.era}>
        <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {PC_ERAS.map((era) => {
            const selected = form.era === era.value
            return (
              <button
                key={era.value}
                type="button"
                disabled={submitting}
                onClick={() => onFieldChange('era', era.value)}
                aria-pressed={selected}
                className={`rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors ${
                  selected
                    ? 'border-[#ff8a5c] bg-[#ff8a5c]/10 text-[#ff8a5c] dark:bg-[#ff8a5c]/20'
                    : 'border-neutral-200 text-neutral-700 hover:border-neutral-400 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-neutral-500 dark:hover:bg-surface-800'
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {era.label}
              </button>
            )
          })}
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

      <div className="border-t border-neutral-200 pt-4 dark:border-neutral-700">
        <h4 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
          OS Image
        </h4>

        <FormField
          label="Base Image Path"
          htmlFor="env-base"
          hint="Full path to the locked base image file (never modified)"
        >
          <PathInput
            id="env-base"
            mode="file"
            accept=".img,.iso,.vhd,.cue,.chd,.xiso"
            value={form.base_image_path}
            onChange={(v) => onFieldChange('base_image_path', v)}
            placeholder="/path/to/images/os/win98/base.img"
            className="mt-1"
          />
          {form.era && (
            <FileUpload
              era={form.era}
              mediaType="os"
              accept=".img,.iso,.vhd,.cue,.chd,.xiso"
              onComplete={(path) => onFieldChange('base_image_path', path)}
            />
          )}
        </FormField>

        <FormField
          label="Working Image Path"
          htmlFor="env-working"
          hint="Full path to the working copy used for all launches"
        >
          <PathInput
            id="env-working"
            mode="file"
            accept=".img,.iso,.vhd,.cue,.chd,.xiso"
            value={form.working_image_path}
            onChange={(v) => onFieldChange('working_image_path', v)}
            placeholder="/path/to/images/os/win98/working.img"
            className="mt-1"
          />
          {form.era && (
            <FileUpload
              era={form.era}
              mediaType="os"
              accept=".img,.iso,.vhd,.cue,.chd,.xiso"
              onComplete={(path) => onFieldChange('working_image_path', path)}
            />
          )}
        </FormField>
      </div>

      <FormField label="Notes" htmlFor="env-notes">
        <Textarea
          id="env-notes"
          value={form.notes}
          onChange={(e) => onFieldChange('notes', e.target.value)}
          placeholder="Optional notes about this environment"
        />
      </FormField>

      {submitError && (
        <p role="alert" className="text-sm text-error">
          ❌ {submitError}
        </p>
      )}
    </Modal>
  )
}
