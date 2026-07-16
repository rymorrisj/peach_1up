import { Button, FormField, Input, Textarea } from '@/ui'
import PathInput from '@/components/common/PathInput'
import FileBrowser from '@/components/common/FileBrowser'
import { ERA_LABELS, RATING_OPTIONS } from '@/generated/constants'
import { ERA_TO_EMULATOR, isPcEra } from '@/pages/Environments/EnvironmentModal'
import { PlatformField } from './PlatformField'
import type { SoftwareGameForm as EditFormFields } from '../types/gameForm'
import type { components } from '@shared/types'

type LaunchProfile = components['schemas']['ProfileItemRead']
type Platform = components['schemas']['EnvironmentItemRead']

type EditableItem = {
  era: string
  detection_reason?: string | null
  file_path?: string | null
  folder_path?: string | null
}

const SELECT_CLASS =
  'w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100'

interface EditFormProps {
  item: EditableItem
  form: EditFormFields
  setField: <K extends keyof EditFormFields>(key: K, value: EditFormFields[K]) => void
  handleSave: () => void
  saving: boolean
  saveError: string | null
  saveSuccess: boolean
  execBrowserOpen: boolean
  setExecBrowserOpen: (open: boolean) => void
  launchCommands?: string[] | null
  setLaunchCommands?: (cmds: string[]) => void
  profiles: LaunchProfile[]
  platforms: Platform[]
}

export function EditForm({
  item,
  form,
  setField,
  handleSave,
  saving,
  saveError,
  saveSuccess,
  execBrowserOpen,
  setExecBrowserOpen,
  profiles,
  platforms,
}: EditFormProps) {
  const ROM_ERAS = new Set(['nes', 'n64', 'ps1', 'ps2', 'xbox', 'dreamcast'])
  const isRomEra = ROM_ERAS.has(item.era)
  const showLaunchFile = item.file_path !== undefined || item.folder_path !== undefined
  const eraLabel = ERA_LABELS[item.era] ?? (item.era === 'unknown' ? 'Unknown' : item.era)
  const effectiveProfileId = form.profile_item_id ? parseInt(form.profile_item_id, 10) : null
  const eraProfiles = profiles.filter((p) => p.era === item.era)
  const otherProfiles = profiles.filter((p) => p.era !== item.era)
  const chosenProfile = profiles.find((p) => p.id === effectiveProfileId) ?? null
  const expectedEmulator = (ERA_TO_EMULATOR as Record<string, string | undefined>)[item.era]
  const profileEraMismatch =
    chosenProfile && expectedEmulator != null && chosenProfile.emulator_slug !== expectedEmulator
  const isPcLaunchable = isPcEra(form.era)

  // Console items have no per-item Environment (fixed era-to-emulator
  // mapping), so switching away from a PC era clears any previously
  // selected environment_item_id rather than leaving a stale value that
  // would 422 against the console+environment backend rule on save.
  // Mirrors AppEditForm's handleEraChange for the same reason.
  function handleEraChange(era: string) {
    setField('era', era)
    if (!isPcEra(era)) setField('environment_item_id', '')
  }

  return (
    <section className="space-y-4">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Details
      </h2>

      <div className="grid grid-cols-2 gap-4">
        <FormField label="Title" htmlFor="detail-title" required>
          <Input
            id="detail-title"
            value={form.title}
            onChange={(e) => setField('title', e.target.value)}
            placeholder="Game or software title"
          />
        </FormField>

        <FormField label="Sort Title" htmlFor="detail-sort-title" hint="Used for alphabetical sorting (e.g. 'Doom, The')">
          <Input
            id="detail-sort-title"
            value={form.sort_title}
            onChange={(e) => setField('sort_title', e.target.value)}
            placeholder="Optional"
          />
        </FormField>
      </div>

      <FormField label="Description" htmlFor="detail-description">
        <Textarea
          id="detail-description"
          value={form.description}
          onChange={(e) => setField('description', e.target.value)}
          placeholder="Short description…"
          rows={3}
        />
      </FormField>

      <div className="grid grid-cols-2 gap-4">
        <FormField label="Publisher" htmlFor="detail-publisher">
          <Input
            id="detail-publisher"
            value={form.publisher}
            onChange={(e) => setField('publisher', e.target.value)}
            placeholder="Publisher name"
          />
        </FormField>

        <FormField label="Year" htmlFor="detail-year">
          <Input
            id="detail-year"
            type="number"
            min={1950}
            max={2099}
            value={form.year}
            onChange={(e) => setField('year', e.target.value)}
            placeholder="1993"
          />
        </FormField>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <FormField
          label="Category (custom)"
          htmlFor="detail-category"
          hint="Your own free-text label — separate from the fetched Genre field above, which comes from metadata enrichment."
        >
          <Input
            id="detail-category"
            value={form.category}
            onChange={(e) => setField('category', e.target.value)}
            placeholder="e.g. Action, RPG"
          />
        </FormField>

        <FormField label="Content Rating" htmlFor="detail-rating">
          <select
            id="detail-rating"
            value={form.content_rating}
            onChange={(e) => setField('content_rating', e.target.value)}
            className={SELECT_CLASS}
          >
            {RATING_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </FormField>
      </div>

      <FormField label="Cover Art Path" htmlFor="detail-cover">
        <PathInput
          id="detail-cover"
          mode="file"
          accept=".png,.jpg,.jpeg,.webp"
          value={form.cover_art_path}
          onChange={(v) => setField('cover_art_path', v)}
          placeholder="C:\Images\cover.png"
        />
      </FormField>

      {showLaunchFile && <FormField label="Launch File" htmlFor="detail-executable">
        <div className="flex items-center gap-2">
          <span
            className="min-w-0 flex-1 truncate rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-surface-800"
            title={form.executable_path || undefined}
          >
            {form.executable_path
              ? <span className="font-mono text-neutral-700 dark:text-neutral-300">{form.executable_path.split(/[\\/]/).pop()}</span>
              : <span className="italic text-neutral-400 dark:text-neutral-500">No launch file detected — browse to set one.</span>
            }
          </span>
          <Button
            variant="secondary"
            size="sm"
            className="shrink-0"
            onClick={() => setExecBrowserOpen(true)}
          >
            Browse…
          </Button>
        </div>
        <FileBrowser
          open={execBrowserOpen}
          onClose={() => setExecBrowserOpen(false)}
          onSelect={(path) => { setField('executable_path', path); setExecBrowserOpen(false) }}
          mode="file"
          extensions="cue,iso,chd,xiso,exe"
          title="Select Launch File"
          rootPath={item.folder_path ?? null}
        />
        <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
          {isRomEra
            ? 'ROM-based media — auto-resolved from your media folder. Override below if it picked the wrong file.'
            : 'The file Peach 1UP will launch. Auto-detected from your media folder — override if incorrect.'}
        </p>
      </FormField>}

      <div className="grid grid-cols-2 gap-4">
        <FormField label="Era" htmlFor="detail-era">
          <select
            id="detail-era"
            value={form.era}
            onChange={(e) => handleEraChange(e.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">— No era —</option>
            {Object.entries(ERA_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          {item.detection_reason ? (
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              Era was detected automatically from your media. You can change it if the detection was wrong.
              {' '}<span className="italic">Detected because: {item.detection_reason}</span>
            </p>
          ) : (item.era === 'unknown' || !item.era) ? (
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
              Era could not be detected automatically. Please select one.
            </p>
          ) : null}
        </FormField>

        <PlatformField
          isPcLaunchable={isPcLaunchable}
          itemEra={form.era}
          value={form.environment_item_id}
          onChange={(v) => setField('environment_item_id', v)}
          platforms={platforms}
          disabledNote="Determined automatically by era, no environment needed."
        />
      </div>

      <FormField label="Launch Profile" htmlFor="detail-profile">
        <select
          id="detail-profile"
          value={form.profile_item_id}
          onChange={(e) => setField('profile_item_id', e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">— No profile —</option>
          {eraProfiles.length > 0 && (
            <optgroup label={`Matching era (${eraLabel})`}>
              {eraProfiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.is_bundled ? ' (default)' : ''}
                </option>
              ))}
            </optgroup>
          )}
          {otherProfiles.length > 0 && (
            <optgroup label="Other eras">
              {otherProfiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({ERA_LABELS[p.era] ?? p.era})
                </option>
              ))}
            </optgroup>
          )}
        </select>
        {profileEraMismatch && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Selected profile targets a different era — launch may fail.
          </p>
        )}
      </FormField>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} loading={saving}>
          Save Changes
        </Button>
        {saveSuccess && (
          <span className="text-sm text-green-600 dark:text-green-400">Saved ✓</span>
        )}
      </div>

      {saveError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {saveError}
        </p>
      )}
    </section>
  )
}
