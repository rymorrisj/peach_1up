import { Button, FormField, Input, Modal, Textarea } from '@/ui'
import LaunchCommandList from '@/components/LaunchCommandList'
import { DGVOODOO2_SUPPORTED_ERAS } from '@/generated/constants'
import type { EmulatorCatalogSlug } from '@/generated/constants'
import type { DriveMode, DriveRecord, EmulatorEntry, ProfileForm, ProfileModalState } from '@/types/profiles'

const ERA_DEFAULT_DRIVE_SIZE: Record<string, number> = {
  dos: 500, win31: 500, win95: 2048, win98: 4096, winxp: 8192,
}

const SELECT_CLASS =
  'w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100'

interface ProfilesTabFormModalProps {
  modal: ProfileModalState
  form: ProfileForm
  formErrors: Partial<Record<keyof ProfileForm, string>>
  submitError: string | null
  submitting: boolean
  emulators: EmulatorEntry[]
  drives: DriveRecord[]
  eraOptions: Array<{ value: string; label: string }>
  emulatorOptions: Array<{ value: string; label: string }>
  setField: <K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) => void
  onSubmit: () => void
  onClose: () => void
}

export function ProfilesTabFormModal({
  modal, form, formErrors, submitError, submitting, emulators, drives, eraOptions, emulatorOptions, setField, onSubmit, onClose,
}: ProfilesTabFormModalProps) {
  const modalTitle = modal?.mode === 'create' ? 'Add Launch Profile' : 'Edit Launch Profile'

  return (
    <Modal
      open={modal !== null}
      title={modalTitle}
      onClose={onClose}
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

      <FormField label="Emulator Slug" htmlFor="lp-emulator" required error={formErrors.emulator_slug}>
        <select
          id="lp-emulator"
          value={form.emulator_slug}
          onChange={(e) => setField('emulator_slug', e.target.value as EmulatorCatalogSlug | '')}
          className={SELECT_CLASS}
        >
          <option value="">— Select emulator —</option>
          {emulatorOptions.map((e) => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </select>
      </FormField>

      <FormField label="Era" htmlFor="lp-era" required error={formErrors.era}>
        <select
          id="lp-era"
          value={form.era}
          onChange={(e) => setField('era', e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">— Select era —</option>
          {eraOptions.map((e) => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </select>
      </FormField>

      <FormField
        label="Extra Arguments"
        htmlFor="lp-args"
        hint="Additional command-line flags passed to the emulator"
      >
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
              form.enable_networking ? 'bg-[#ff8a5c]' : 'bg-neutral-300 dark:bg-neutral-600'
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
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#ff8a5c] focus:ring-offset-2 ${
                form.enable_dgvoodoo2 ? 'bg-[#ff8a5c]' : 'bg-neutral-300 dark:bg-neutral-600'
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

      <FormField label="Launch commands" hint="Default commands run when launching software with this profile">
        <LaunchCommandList
          value={form.launch_commands}
          onChange={(v) => setField('launch_commands', v)}
          disabled={submitting}
        />
      </FormField>

      {emulators.find((e) => e.slug === form.emulator_slug)?.container_enabled && (
        <FormField
          label="AppContainer"
          htmlFor="lp-container"
          hint="Override the emulator's default AppContainer setting for this profile"
        >
          <select
            id="lp-container"
            value={form.container_enabled === null ? '' : form.container_enabled ? 'true' : 'false'}
            onChange={(e) => {
              const v = e.target.value
              setField('container_enabled', v === '' ? null : v === 'true')
            }}
            className={SELECT_CLASS}
          >
            <option value="">Default (use emulator setting)</option>
            <option value="true">Enabled</option>
            <option value="false">Disabled</option>
          </select>
        </FormField>
      )}

      <FormField label="Persistent drive" htmlFor="lp-drive-mode">
        <select
          id="lp-drive-mode"
          value={form.drive_mode}
          onChange={(e) => {
            const mode = e.target.value as DriveMode
            setField('drive_mode', mode)
            if (mode === 'create' && !form.new_drive_name) {
              setField('new_drive_name', form.slug ? `${form.slug}-drive` : '')
              setField('new_drive_size_mb', ERA_DEFAULT_DRIVE_SIZE[form.era] ?? 500)
            }
          }}
          className={SELECT_CLASS}
        >
          <option value="none">No drive</option>
          <option value="existing">Use existing drive</option>
          <option value="create">Create new drive</option>
        </select>
        {form.drive_mode === 'none' && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Without a drive, sound configuration and save files will not persist between sessions.
          </p>
        )}
      </FormField>

      {form.drive_mode === 'existing' && (
        <FormField label="Select drive" htmlFor="lp-drive-slug" error={formErrors.drive_slug}>
          <select
            id="lp-drive-slug"
            value={form.drive_slug}
            onChange={(e) => setField('drive_slug', e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">— Select a drive —</option>
            {drives.map((d) => (
              <option key={d.slug} value={d.slug}>
                {d.name} ({d.size_mb} MB, {d.era})
              </option>
            ))}
          </select>
        </FormField>
      )}

      {form.drive_mode === 'create' && (
        <>
          <FormField label="Drive name" htmlFor="lp-drive-name" error={formErrors.new_drive_name}>
            <Input
              id="lp-drive-name"
              value={form.new_drive_name}
              onChange={(e) => setField('new_drive_name', e.target.value)}
              placeholder={`${form.slug || 'profile'}-drive`}
              hasError={!!formErrors.new_drive_name}
            />
          </FormField>
          <FormField label="Drive size (MB)" htmlFor="lp-drive-size">
            <Input
              id="lp-drive-size"
              type="number"
              min={64}
              max={32768}
              value={form.new_drive_size_mb}
              onChange={(e) => setField('new_drive_size_mb', parseInt(e.target.value, 10) || 500)}
            />
          </FormField>
        </>
      )}

      {submitError && (
        <p role="alert" className="text-sm text-error">
          ❌ {submitError}
        </p>
      )}
    </Modal>
  )
}
