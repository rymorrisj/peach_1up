import {
  canOfferPlatformConfirm,
  platformHintText,
  type PlatformConfirmInputs,
} from './platformReview';

const ADVICE =
  "If the game won't launch, look up the correct platform (e.g. PS1, Xbox) and set it manually.";

describe('platformHintText', () => {
  it('unreviewed with a reason names where the platform was detected from', () => {
    expect(platformHintText('unreviewed', 'ps2', 'CHD header')).toBe(
      `Highlighted because this platform was detected, not verified. Detected from: CHD header. ${ADVICE}`,
    );
  });

  it('unreviewed omits the detected-from clause when the reason is empty', () => {
    const expected = `Highlighted because this platform was detected, not verified. ${ADVICE}`;
    expect(platformHintText('unreviewed', 'ps2', '')).toBe(expected);
    expect(platformHintText('unreviewed', 'ps2', null)).toBe(expected);
    expect(platformHintText('unreviewed', 'ps2', '   ')).toBe(expected);
  });

  it('unreviewed with an unknown platform says nothing was detected, even with a reason', () => {
    const expected = `No platform was detected. ${ADVICE}`;
    expect(platformHintText('unreviewed', 'unknown', null)).toBe(expected);
    expect(platformHintText('unreviewed', 'unknown', 'CHD header')).toBe(expected);
    expect(platformHintText('unreviewed', '', 'CHD header')).toBe(expected);
  });

  it('verified says it was checked against the hash index', () => {
    expect(platformHintText('verified', 'ps1', 'CHD header')).toBe(
      `Verified against the hash index. ${ADVICE}`,
    );
  });

  it('confirmed says so and keeps the detected-from clause when there is a reason', () => {
    expect(platformHintText('confirmed', 'ps1', 'Selected by user during import')).toBe(
      `This platform is confirmed. Detected from: Selected by user during import. ${ADVICE}`,
    );
  });

  it('confirmed omits the detected-from clause when the reason is empty', () => {
    expect(platformHintText('confirmed', 'ps1', null)).toBe(
      `This platform is confirmed. ${ADVICE}`,
    );
  });

  it('every state ends with the set-it-manually advice', () => {
    for (const review of ['unreviewed', 'verified', 'confirmed'] as const) {
      expect(platformHintText(review, 'ps1', 'x').endsWith(ADVICE)).toBe(true);
    }
  });

  it('passes a disc-supplied reason through untouched, as plain text', () => {
    const reason = '<img src=x onerror=alert(1)> LABEL';
    expect(platformHintText('unreviewed', 'ps1', reason)).toContain(`Detected from: ${reason}.`);
  });
});

describe('canOfferPlatformConfirm', () => {
  const offered: PlatformConfirmInputs = {
    platformReview: 'unreviewed',
    hasLaunched: true,
    canManageGame: true,
    platform: 'ps1',
    platformEditPending: false,
  };

  it('is offered when unreviewed, launched, allowed, platform known and no platform edit pending', () => {
    expect(canOfferPlatformConfirm(offered)).toBe(true);
  });

  it.each(['confirmed', 'verified', undefined] as const)(
    'is hidden when platform_review is %s',
    (platformReview) => {
      expect(canOfferPlatformConfirm({ ...offered, platformReview })).toBe(false);
    },
  );

  it.each([false, null, undefined] as const)('is hidden when has_launched is %s', (hasLaunched) => {
    expect(canOfferPlatformConfirm({ ...offered, hasLaunched })).toBe(false);
  });

  it('is hidden without permission to manage games', () => {
    expect(canOfferPlatformConfirm({ ...offered, canManageGame: false })).toBe(false);
  });

  it.each(['unknown', '', null, undefined] as const)(
    'is hidden when platform is %s',
    (platform) => {
      expect(canOfferPlatformConfirm({ ...offered, platform })).toBe(false);
    },
  );

  it('is hidden while the form holds an unsaved platform change', () => {
    expect(canOfferPlatformConfirm({ ...offered, platformEditPending: true })).toBe(false);
  });
});
