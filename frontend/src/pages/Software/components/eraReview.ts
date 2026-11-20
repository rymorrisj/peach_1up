// Pure rules for the era field's trust treatment. era_review itself is computed
// by the backend (see _compute_era_review in backend/models/game.py), this file
// only decides what to show for it: the hover hint text and whether the
// "Confirm platform" action is offered.

export type EraReview = 'confirmed' | 'verified' | 'unreviewed';

const FALLBACK_ADVICE =
  "If the game won't launch, look up the correct platform (e.g. PS1, Xbox) and set the era manually.";

function isUnknownEra(era: string | null | undefined): boolean {
  return !era || era === 'unknown';
}

function detectedFromClause(reason: string | null | undefined): string {
  const trimmed = reason?.trim();
  return trimmed ? ` Detected from: ${trimmed}.` : '';
}

// Plain text only. `reason` can carry disc-supplied strings (a volume label),
// so callers must render the result as a text node, never as HTML.
export function eraHintText(
  review: EraReview,
  era: string | null | undefined,
  reason: string | null | undefined,
): string {
  let lead: string;
  if (review === 'verified') {
    lead = 'Verified against the hash index.';
  } else if (review === 'confirmed') {
    lead = `This platform is confirmed.${detectedFromClause(reason)}`;
  } else if (isUnknownEra(era)) {
    lead = 'No platform was detected.';
  } else {
    lead = `Highlighted because this platform was detected, not verified.${detectedFromClause(reason)}`;
  }
  return `${lead} ${FALLBACK_ADVICE}`;
}

export interface EraConfirmInputs {
  eraReview: EraReview | undefined;
  hasLaunched: boolean | null | undefined;
  canManageGame: boolean;
  // The saved era, not the form's.
  era: string | null | undefined;
  // True while the form holds an era different from the saved one.
  eraEditPending: boolean;
}

// The Confirm button is for an era that is still a guess, on a game that has
// actually been launched, for someone allowed to edit it, with no era edit in
// flight. has_launched is null on list reads, only a literal true counts.
export function canOfferEraConfirm(inputs: EraConfirmInputs): boolean {
  return (
    inputs.eraReview === 'unreviewed' &&
    inputs.hasLaunched === true &&
    inputs.canManageGame &&
    !isUnknownEra(inputs.era) &&
    !inputs.eraEditPending
  );
}
