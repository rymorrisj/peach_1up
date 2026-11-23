import type { ReactNode } from 'react';
import { Checkbox } from '@/ui';
import { ratingChangeReasonText, type RatingChangeDetail } from '@/hooks/useRatingChangeConfirm';
import { FetchAssetPicker } from './FetchAssetPicker';
import { webLinks } from './externalLinks';
import {
  normalizeContentRating,
  type EnrichSelection,
  type FieldKey,
  type GameDetails,
  type ReviewField,
} from './metadataReview';

interface ReviewRowProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  current: string;
  fetched: string;
  disabled?: boolean;
  children?: ReactNode;
}

function ReviewRow({
  label,
  checked,
  onChange,
  current,
  fetched,
  disabled,
  children,
}: ReviewRowProps) {
  const unavailable = fetched === '';
  return (
    <li className="space-y-1.5 rounded-md border border-neutral-700 px-3 py-2">
      <Checkbox
        checked={checked && !unavailable}
        onCheckedChange={onChange}
        disabled={disabled || unavailable}
        label={label}
        labelClassName="font-medium"
      />
      <dl className="grid grid-cols-[4.5rem_1fr] gap-x-2 gap-y-0.5 text-xs">
        <dt className="text-neutral-400">Current</dt>
        <dd className="line-clamp-3 text-neutral-300">{current || 'Empty'}</dd>
        <dt className="text-neutral-400">Fetched</dt>
        <dd className="line-clamp-3 text-neutral-100">{fetched || 'Not provided'}</dd>
      </dl>
      {children}
    </li>
  );
}

function linksSummary(details: GameDetails): string {
  const total = details.external_links.length;
  if (total === 0) return '';
  const trailers = details.external_links.filter((l) => l.type === 'trailer').length;
  const sites = total - trailers;
  return [
    trailers > 0 ? `${trailers} trailer${trailers === 1 ? '' : 's'}` : '',
    sites > 0 ? `${sites} link${sites === 1 ? '' : 's'}` : '',
  ]
    .filter(Boolean)
    .join(', ');
}

interface FetchReviewStepProps {
  details: GameDetails;
  fields: ReviewField[];
  currentRating: string | null;
  currentLinks: readonly unknown[] | null | undefined;
  selection: EnrichSelection;
  onSelectionChange: (next: EnrichSelection) => void;
  ratingConflict: RatingChangeDetail | null;
  confirmRating: boolean;
  onConfirmRating: (confirmed: boolean) => void;
  assetSelected: Set<string>;
  onToggleAsset: (url: string, on: boolean) => void;
  coverUrl: string | null;
  onCoverChange: (url: string | null) => void;
  disabled: boolean;
}

export function FetchReviewStep({
  details,
  fields,
  currentRating,
  currentLinks,
  selection,
  onSelectionChange,
  ratingConflict,
  confirmRating,
  onConfirmRating,
  assetSelected,
  onToggleAsset,
  coverUrl,
  onCoverChange,
  disabled,
}: FetchReviewStepProps) {
  const unresolvedGenreIds = details.unresolved_genre_ids ?? [];
  const fetchedRating = details.rating?.trim() ? details.rating.trim() : '';
  const normalizedRating = normalizeContentRating(fetchedRating);
  const ratingText = !fetchedRating
    ? ''
    : normalizedRating
      ? normalizedRating === fetchedRating
        ? normalizedRating
        : `${normalizedRating} (from "${fetchedRating}")`
      : `Not recognised (from "${fetchedRating}"), it would be stored as unrated`;
  const currentLinkCount = webLinks(currentLinks).length;

  function setField(key: FieldKey, on: boolean) {
    onSelectionChange({ ...selection, fields: { ...selection.fields, [key]: on } });
  }

  return (
    <div className="space-y-4">
      <ul className="space-y-2">
        {fields.map((f) => (
          <ReviewRow
            key={f.key}
            label={f.label}
            checked={selection.fields[f.key]}
            onChange={(on) => setField(f.key, on)}
            current={f.current}
            fetched={f.fetched}
            disabled={disabled}
          />
        ))}

        <ReviewRow
          label="Content rating"
          checked={selection.rating}
          onChange={(on) => onSelectionChange({ ...selection, rating: on })}
          current={currentRating ?? ''}
          fetched={ratingText}
          disabled={disabled}
        >
          {ratingConflict && selection.rating && (
            <div
              role="alert"
              className="space-y-2 rounded-md border border-amber-600/50 bg-amber-950/30 p-3"
            >
              <p className="text-sm text-amber-300">
                Nothing was applied. {ratingChangeReasonText(ratingConflict)} Currently{' '}
                <strong>{ratingConflict.current_rating ?? 'unrated'}</strong>, would become{' '}
                <strong>{ratingConflict.new_rating ?? 'unrated'}</strong>. Confirm below, or untick
                this row to apply the rest without a rating.
              </p>
              <Checkbox
                checked={confirmRating}
                onCheckedChange={onConfirmRating}
                disabled={disabled}
                label="I understand and want to apply this rating change"
                labelClassName="text-amber-200"
              />
            </div>
          )}
        </ReviewRow>

        <ReviewRow
          label="Links"
          checked={selection.links}
          onChange={(on) => onSelectionChange({ ...selection, links: on })}
          current={currentLinkCount > 0 ? `${currentLinkCount} saved` : ''}
          fetched={linksSummary(details)}
          disabled={disabled}
        />
      </ul>

      {unresolvedGenreIds.length > 0 && (
        <div role="alert" className="rounded-md border border-amber-600/50 bg-amber-950/30 p-3">
          <p className="text-sm text-amber-300">
            {unresolvedGenreIds.length === 1 ? '1 genre' : `${unresolvedGenreIds.length} genres`}{' '}
            could not be matched and will not be applied. Unmatched provider genre ids:{' '}
            <strong>{unresolvedGenreIds.join(', ')}</strong>.
          </p>
        </div>
      )}

      {details.assets.length > 0 && (
        <FetchAssetPicker
          assets={details.assets}
          selected={assetSelected}
          onToggle={onToggleAsset}
          coverUrl={coverUrl}
          onCoverChange={onCoverChange}
          disabled={disabled}
        />
      )}
    </div>
  );
}
