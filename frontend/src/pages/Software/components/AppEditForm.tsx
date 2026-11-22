import { Button, Card, FormField, Input, Textarea, Select } from '@/ui';
import PathInput from '@/components/common/PathInput';
import { isPcPlatform } from '@/pages/Environments/environmentForm';
import { platformSelectOptions } from '@/types/platform';
import { EnvironmentField } from './EnvironmentField';
import type { SoftwareAppForm } from '../types/appForm';

interface AppEditFormProps {
  form: SoftwareAppForm;
  setField: <K extends keyof SoftwareAppForm>(key: K, value: SoftwareAppForm[K]) => void;
  handleSave: () => void;
  saving: boolean;
  saveError: string | null;
  saveSuccess: boolean;
}

export function AppEditForm({
  form,
  setField,
  handleSave,
  saving,
  saveError,
  saveSuccess,
}: AppEditFormProps) {
  // is_pc is derived from platform on the backend, not independently settable
  // (see appForm.ts), so changing platform here keeps is_pc in sync locally and
  // clears environment_item_id when the new platform is console, rather than
  // leaving a stale value that would 422 against the console+environment
  // rule (_enforce_environment_binding) on save.
  function handlePlatformChange(platform: string) {
    const isPc = isPcPlatform(platform);
    setField('platform', platform);
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
            label="Platform"
            htmlFor="detail-platform"
            hint={
              form.platform
                ? form.is_pc
                  ? 'PC app, choose an Environment below before this can launch.'
                  : 'Console app, no Environment needed.'
                : undefined
            }
          >
            <Select
              id="detail-platform"
              value={form.platform || 'none'}
              onValueChange={(v) => handlePlatformChange(v === 'none' ? '' : v)}
              options={platformSelectOptions('No platform selected')}
            />
          </FormField>

          <EnvironmentField
            platform={form.platform}
            value={form.environment_item_id}
            onChange={(v) => setField('environment_item_id', v)}
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
