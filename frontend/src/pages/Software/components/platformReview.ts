// Pure rules for the platform field's trust treatment. platform_review itself is computed
// by the backend (see _compute_platform_review in backend/models/game.py), this file
// only decides what to show for it: the hover hint text and whether the
// "Confirm platform" action is offered.

export type PlatformReview = 'confirmed' | 'verified' | 'unreviewed';

const FALLBACK_ADVICE =
  "If the game won't launch, look up the correct platform (e.g. PS1, Xbox) and set it manually.";

function isUnknownPlatform(platform: string | null | undefined): boolean {
  return !platform || platform === 'unknown';
}

function detectedFromClause(reason: string | null | undefined): string {
  const trimmed = reason?.trim();
  return trimmed ? ` Detected from: ${trimmed}.` : '';
}

// Plain text only. `reason` can carry disc-supplied strings (a volume label),
// so callers must render the result as a text node, never as HTML.
export function platformHintText(
  review: PlatformReview,
  platform: string | null | undefined,
  reason: string | null | undefined,
): string {
  let lead: string;
  if (review === 'verified') {
    lead = 'Verified against the hash index.';
  } else if (review === 'confirmed') {
    lead = `This platform is confirmed.${detectedFromClause(reason)}`;
  } else if (isUnknownPlatform(platform)) {
    lead = 'No platform was detected.';
  } else {
    lead = `Highlighted because this platform was detected, not verified.${detectedFromClause(reason)}`;
  }
  return `${lead} ${FALLBACK_ADVICE}`;
}

export interface PlatformConfirmInputs {
  platformReview: PlatformReview | undefined;
  hasLaunched: boolean | null | undefined;
  canManageGame: boolean;
  // The saved platform, not the form's.
  platform: string | null | undefined;
  // True while the form holds a platform different from the saved one.
  platformEditPending: boolean;
}

// The Confirm button is for a platform that is still a guess, on a game that has
// actually been launched, for someone allowed to edit it, with no platform edit in
// flight. has_launched is null on list reads, only a literal true counts.
export function canOfferPlatformConfirm(inputs: PlatformConfirmInputs): boolean {
  return (
    inputs.platformReview === 'unreviewed' &&
    inputs.hasLaunched === true &&
    inputs.canManageGame &&
    !isUnknownPlatform(inputs.platform) &&
    !inputs.platformEditPending
  );
}
