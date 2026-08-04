import { Button, Card, FormField, Input, Textarea } from '@/ui';
import PathInput from '@/components/common/PathInput';
import type { SoftwareMediaForm } from '../types/mediaForm';

interface MediaEditFormProps {
  form: SoftwareMediaForm;
  setField: <K extends keyof SoftwareMediaForm>(key: K, value: SoftwareMediaForm[K]) => void;
  handleSave: () => void;
  saving: boolean;
  saveError: string | null;
  saveSuccess: boolean;
}

export function MediaEditForm({
  form,
  setField,
  handleSave,
  saving,
  saveError,
  saveSuccess,
}: MediaEditFormProps) {
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
              placeholder="Media title"
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
