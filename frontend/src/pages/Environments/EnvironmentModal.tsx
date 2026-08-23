import { useState } from 'react';
import { Button, FormField, Input, Modal, Textarea } from '@/ui';
import PathInput from '@/components/common/PathInput';
import FileUpload from '@/components/common/FileUpload';
import BrowsePanel from '@/components/common/BrowsePanel';
import LaunchCommandList from '@/components/LaunchCommandList';
import type { HardwareProfile } from '@/generated/constants';
import { ERA_TO_EMULATOR, type EnvironmentForm, type PCEra } from './environmentForm';

const PC_ERAS: { value: PCEra; label: string }[] = [
  { value: 'dos', label: 'DOS' },
  { value: 'win95', label: 'Windows 95' },
  { value: 'win98', label: 'Windows 98' },
  { value: 'winxp', label: 'Windows XP' },
];

const EMULATOR_LABELS: Record<string, string> = {
  'dosbox-x': 'DOSBox-X',
  '86box': '86Box',
};

const BOX86_ERAS = new Set<PCEra>(['win95', 'win98', 'winxp']);
const INSTALL_MEDIA_ERAS = new Set<PCEra>(['win95', 'win98', 'winxp']);

const HARDWARE_PROFILES: { value: HardwareProfile; label: string; description: string }[] = [
  {
    value: 'standard',
    label: 'Standard',
    description: 'Works for most software. Good 2D performance.',
  },
  {
    value: '3d_glide',
    label: '3D / Glide',
    description: 'For 3dfx titles: Tomb Raider, NFS, Quake. Requires Voodoo drivers after install.',
  },
  {
    value: 'dos_fm',
    label: 'DOS / FM Music',
    description: 'For older DOS games run under Windows with AdLib/OPL music.',
  },
  {
    value: 'midi',
    label: 'MIDI Music',
    description: 'For strategy and adventure games with Roland MIDI soundtracks (C&C, X-COM, etc.)',
  },
];

interface EnvironmentModalProps {
  open: boolean;
  mode: 'create' | 'edit';
  /** The Environment's slug, only defined in edit mode, once the record (and
   *  its slug) already exist. Install-media upload resolves the target
   *  Environment by slug server-side, so it has nothing to upload to yet
   *  during create; FileUpload renders nothing when this is undefined. */
  slug?: string;
  form: EnvironmentForm;
  formErrors: Partial<Record<keyof EnvironmentForm, string>>;
  submitError: string | null;
  submitting: boolean;
  onClose: () => void;
  onSubmit: () => void;
  onFieldChange: <K extends keyof EnvironmentForm>(key: K, value: EnvironmentForm[K]) => void;
}

export default function EnvironmentModal({
  open,
  mode,
  slug,
  form,
  formErrors,
  submitError,
  submitting,
  onClose,
  onSubmit,
  onFieldChange,
}: EnvironmentModalProps) {
  const emulatorLabel = form.era ? (EMULATOR_LABELS[ERA_TO_EMULATOR[form.era]] ?? null) : null;
  const isBox86Era = form.era !== null && BOX86_ERAS.has(form.era);
  const showInstallMediaAbove =
    form.era !== null && INSTALL_MEDIA_ERAS.has(form.era) && mode === 'create';
  const hasAdvancedValues = !!(
    (!showInstallMediaAbove && form.base_image_path) ||
    form.working_image_path ||
    form.machine_override ||
    form.notes ||
    form.launch_commands.length > 0
  );
  const [showAdvanced, setShowAdvanced] = useState(false);
  // Re-seeds showAdvanced from hasAdvancedValues every time the modal
  // (re)opens, without fighting the user's own toggle click while it stays
  // open. Adjusted during render (tracking the previous `open`) rather than
  // in a useEffect, for the same reason as ConfirmModal's checkbox reset;
  // hasAdvancedValues is deliberately excluded from the trigger, matching
  // the original effect's intentionally incomplete deps array.
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) setShowAdvanced(hasAdvancedValues);
  }
  const [machineBrowserOpen, setMachineBrowserOpen] = useState(false);

  return (
    <Modal
      open={open}
      title={mode === 'create' ? 'Add Environment' : 'Edit Environment'}
      onClose={onClose}
      busy={submitting}
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
            const selected = form.era === era.value;
            return (
              <button
                key={era.value}
                type="button"
                disabled={submitting}
                onClick={() => onFieldChange('era', era.value)}
                aria-pressed={selected}
                className={`rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors ${
                  selected
                    ? 'border-accent bg-accent/10 text-accent dark:bg-accent/20'
                    : 'border-neutral-200 text-neutral-700 hover:border-neutral-400 hover:bg-surface-2 dark:border-neutral-700 dark:text-neutral-300 dark:hover:border-neutral-500'
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {era.label}
              </button>
            );
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

      {isBox86Era && (
        <div className="border-t border-neutral-200 pt-4 dark:border-neutral-700">
          <h4 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
            Hardware Profile
          </h4>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {HARDWARE_PROFILES.map((profile) => {
              const selected = form.hardware_profile === profile.value;
              return (
                <button
                  key={profile.value}
                  type="button"
                  disabled={submitting}
                  onClick={() => onFieldChange('hardware_profile', profile.value)}
                  aria-pressed={selected}
                  className={`rounded-md border p-3 text-left transition-colors ${
                    selected
                      ? 'border-accent bg-accent/10 dark:bg-accent/20'
                      : 'border-neutral-200 hover:border-neutral-400 hover:bg-surface-2 dark:border-neutral-700 dark:hover:border-neutral-500'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  <span
                    className={`block text-sm font-medium ${
                      selected ? 'text-accent' : 'text-neutral-800 dark:text-neutral-200'
                    }`}
                  >
                    {profile.label}
                  </span>
                  <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
                    {profile.description}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {showInstallMediaAbove && (
        <div className="border-t border-neutral-200 pt-4 dark:border-neutral-700">
          <FormField
            label="Installation Media"
            htmlFor="env-install-media"
            required
            hint="ISO or disk image for this Windows environment. Required to set up a new environment."
            error={formErrors.base_image_path}
          >
            <PathInput
              id="env-install-media"
              mode="file"
              accept=".iso,.img,.vhd,.cue,.chd"
              value={form.base_image_path}
              onChange={(v) => onFieldChange('base_image_path', v)}
              placeholder="/path/to/win98.iso"
              className="mt-1"
              hasError={!!formErrors.base_image_path}
            />
            {form.era && (
              <FileUpload
                slug={slug}
                accept=".iso,.img,.vhd,.cue,.chd"
                onComplete={(path) => onFieldChange('base_image_path', path)}
              />
            )}
          </FormField>
        </div>
      )}

      <div className="border-t border-neutral-200 pt-3 dark:border-neutral-700">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-medium text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          <span>{showAdvanced ? '▾' : '▸'}</span>
          Advanced
        </button>

        {showAdvanced && (
          <div className="mt-3 space-y-4">
            {!showInstallMediaAbove && (
              <FormField
                label="Base Image Path"
                htmlFor="env-base"
                hint="Provide an ISO or disk image. Peach 1UP will set up the environment automatically."
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
                    slug={slug}
                    accept=".img,.iso,.vhd,.cue,.chd,.xiso"
                    onComplete={(path) => onFieldChange('base_image_path', path)}
                  />
                )}
              </FormField>
            )}

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
                  slug={slug}
                  accept=".img,.iso,.vhd,.cue,.chd,.xiso"
                  onComplete={(path) => onFieldChange('working_image_path', path)}
                />
              )}
            </FormField>

            {isBox86Era && (
              <FormField
                label="Machine Override"
                htmlFor="env-machine"
                hint="Browse your ROM pack to select a specific machine. The folder name is the machine identifier 86Box will use."
              >
                <div className="mt-1 flex items-center gap-2">
                  {form.machine_override ? (
                    <span className="flex-1 truncate font-mono text-sm text-neutral-900 dark:text-neutral-100">
                      {form.machine_override}
                    </span>
                  ) : (
                    <span className="flex-1 text-sm text-neutral-400 dark:text-neutral-500">
                      Using profile default
                    </span>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    className="shrink-0"
                    onClick={() => setMachineBrowserOpen(!machineBrowserOpen)}
                    disabled={submitting}
                  >
                    Browse…
                  </Button>
                  {form.machine_override && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0"
                      onClick={() => onFieldChange('machine_override', '')}
                      disabled={submitting}
                    >
                      Clear
                    </Button>
                  )}
                </div>
                {machineBrowserOpen && (
                  <div className="mt-2">
                    <BrowsePanel
                      open={machineBrowserOpen}
                      onClose={() => setMachineBrowserOpen(false)}
                      onSelect={(path) => {
                        const slug =
                          path.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? '';
                        onFieldChange('machine_override', slug);
                        setMachineBrowserOpen(false);
                      }}
                      mode="folder"
                      title="Select Machine (ROM pack › machines)"
                    />
                  </div>
                )}
              </FormField>
            )}

            <FormField
              label="Launch commands"
              hint="Commands run inside the environment when launching software"
            >
              <LaunchCommandList
                value={form.launch_commands}
                onChange={(v) => onFieldChange('launch_commands', v)}
                disabled={submitting}
              />
            </FormField>

            <FormField label="Notes" htmlFor="env-notes">
              <Textarea
                id="env-notes"
                value={form.notes}
                onChange={(e) => onFieldChange('notes', e.target.value)}
                placeholder="Optional notes about this environment"
              />
            </FormField>
          </div>
        )}
      </div>

      {submitError && (
        <p role="alert" className="text-sm text-error">
          ❌ {submitError}
        </p>
      )}
    </Modal>
  );
}
