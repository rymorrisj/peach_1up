import { Button, Card, FormField, Input, Textarea, Select } from '@/ui';
import PathInput from '@/components/common/PathInput';
import { ERA_LABELS } from '@/generated/constants';
import { ERA_TO_EMULATOR } from '@/pages/Environments/EnvironmentModal';
import { PlatformField } from './PlatformField';
import type { SoftwareAppForm } from '../types/appForm';
import type { components } from '@shared/types';

type Platform = components['schemas']['EnvironmentItemRead'];

interface AppEditFormProps {
  form: SoftwareAppForm;
  setField: <K extends keyof SoftwareAppForm>(key: K, value: SoftwareAppForm[K]) => void;
  handleSave: () => void;
  saving: boolean;
  saveError: string | null;
  saveSuccess: boolean;
  platforms: Platform[];
}

export function AppEditForm({
  form,
  setField,
  handleSave,
  saving,
  saveError,
  saveSuccess,
  platforms,
}: AppEditFormProps) {
  // is_pc is derived from era on the backend, not independently settable
  // (see appForm.ts), so changing era here keeps is_pc in sync locally and
  // clears environment_item_id when the new era is console, rather than
  // leaving a stale value that would 422 against the console+environment
  // rule (_enforce_environment_binding) on save.
  function handleEraChange(era: string) {
    const isPc = era in ERA_TO_EMULATOR;
    setField('era', era);
    setField('is_pc', isPc);
    if (!isPc) setField('environment_item_id', '');
  }

  return (
    <div className="space-y-6">
      <Card>
        <Card.Header>Details</Card.Header>
        <div className="space-y-4">
          <FormField label="Title" htmlFor="detail-title" required>
            <Input
              id="detail-title"
              value={form.title}
              onChange={(e) => setField('title', e.target.value)}
              placeholder="App title"
            />
          </FormField>

          <FormField label="Description" htmlFor="detail-description">
            <Textarea
              id="detail-description"
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
              placeholder="Short description…"
              rows={3}
            />
          </FormField>
        </div>
      </Card>

      <Card>
        <Card.Header>Files</Card.Header>
        <div className="space-y-4">
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
        </div>
      </Card>

      <Card>
        <Card.Header>Launch Setup</Card.Header>
        <div className="space-y-4">
          <FormField
            label="Era"
            htmlFor="detail-era"
            hint={
              form.era
                ? form.is_pc
                  ? 'PC app, an Environment is required before this can launch.'
                  : 'Console app, no Environment needed.'
                : undefined
            }
          >
            <Select
              id="detail-era"
              value={form.era || 'none'}
              onValueChange={(v) => handleEraChange(v === 'none' ? '' : v)}
              options={[
                { value: 'none', label: 'No era selected' },
                ...Object.entries(ERA_LABELS).map(([key, label]) => ({ value: key, label })),
              ]}
            />
          </FormField>

          <PlatformField
            isPcLaunchable={form.is_pc}
            value={form.environment_item_id}
            onChange={(v) => setField('environment_item_id', v)}
            platforms={platforms}
            disabledNote="Determined automatically by platform type, no environment needed."
          />
        </div>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} loading={saving}>
          Save Changes
        </Button>
        {saveSuccess && <span className="text-sm text-green-600 dark:text-green-400">Saved ✓</span>}
      </div>

      {saveError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {saveError}
        </p>
      )}
    </div>
  );
}
