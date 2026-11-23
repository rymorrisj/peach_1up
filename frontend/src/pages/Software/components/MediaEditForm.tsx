import { Button, Card, FormField, Input, Textarea, Select } from '@/ui';
import { RATING_OPTIONS } from '@/generated/constants';
import type { SoftwareMediaForm } from '../types/mediaForm';

// The generated empty option's label is relabelled here so the field shows
// plain "No rating" text.
const MEDIA_RATING_OPTIONS = RATING_OPTIONS.map((o) => ({
  value: o.value || 'none',
  label: o.value ? o.label : 'No rating',
}));

// Rating state from the read model: a bundle linked to software inherits
// its effective rating and has no editable rating of its own.
export interface MediaRatingInheritance {
  isInherited: boolean;
  effectiveRating: string | null;
}

interface MediaEditFormProps {
  form: SoftwareMediaForm;
  setField: <K extends keyof SoftwareMediaForm>(key: K, value: SoftwareMediaForm[K]) => void;
  rating: MediaRatingInheritance;
  handleSave: () => void;
  saving: boolean;
  saveError: string | null;
  saveSuccess: boolean;
}

export function MediaEditForm({
  form,
  setField,
  rating,
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

          {rating.isInherited ? (
            <p className="text-sm text-neutral-600 dark:text-neutral-400">
              Inherited from linked software: {rating.effectiveRating ?? 'Unrated'}
            </p>
          ) : (
            <FormField label="Content Rating" htmlFor="detail-rating">
              <Select
                id="detail-rating"
                value={form.content_rating || 'none'}
                onValueChange={(v) => setField('content_rating', v === 'none' ? '' : v)}
                options={MEDIA_RATING_OPTIONS}
              />
            </FormField>
          )}
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
