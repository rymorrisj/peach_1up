import { canOfferEraConfirm, eraHintText, type EraConfirmInputs } from './eraReview';

const ADVICE =
  "If the game won't launch, look up the correct platform (e.g. PS1, Xbox) and set the era manually.";

describe('eraHintText', () => {
  it('unreviewed with a reason names where the era was detected from', () => {
    expect(eraHintText('unreviewed', 'ps2', 'CHD header')).toBe(
      `Highlighted because this platform was detected, not verified. Detected from: CHD header. ${ADVICE}`,
    );
  });

  it('unreviewed omits the detected-from clause when the reason is empty', () => {
    const expected = `Highlighted because this platform was detected, not verified. ${ADVICE}`;
    expect(eraHintText('unreviewed', 'ps2', '')).toBe(expected);
    expect(eraHintText('unreviewed', 'ps2', null)).toBe(expected);
    expect(eraHintText('unreviewed', 'ps2', '   ')).toBe(expected);
  });

  it('unreviewed with an unknown era says nothing was detected, even with a reason', () => {
    const expected = `No platform was detected. ${ADVICE}`;
    expect(eraHintText('unreviewed', 'unknown', null)).toBe(expected);
    expect(eraHintText('unreviewed', 'unknown', 'CHD header')).toBe(expected);
    expect(eraHintText('unreviewed', '', 'CHD header')).toBe(expected);
  });

  it('verified says it was checked against the hash index', () => {
    expect(eraHintText('verified', 'ps1', 'CHD header')).toBe(
      `Verified against the hash index. ${ADVICE}`,
    );
  });

  it('confirmed says so and keeps the detected-from clause when there is a reason', () => {
    expect(eraHintText('confirmed', 'ps1', 'Selected by user during import')).toBe(
      `This platform is confirmed. Detected from: Selected by user during import. ${ADVICE}`,
    );
  });

  it('confirmed omits the detected-from clause when the reason is empty', () => {
    expect(eraHintText('confirmed', 'ps1', null)).toBe(`This platform is confirmed. ${ADVICE}`);
  });

  it('every state ends with the set-it-manually advice', () => {
    for (const review of ['unreviewed', 'verified', 'confirmed'] as const) {
      expect(eraHintText(review, 'ps1', 'x').endsWith(ADVICE)).toBe(true);
    }
  });

  it('passes a disc-supplied reason through untouched, as plain text', () => {
    const reason = '<img src=x onerror=alert(1)> LABEL';
    expect(eraHintText('unreviewed', 'ps1', reason)).toContain(`Detected from: ${reason}.`);
  });
});

describe('canOfferEraConfirm', () => {
  const offered: EraConfirmInputs = {
    eraReview: 'unreviewed',
    hasLaunched: true,
    canManageGame: true,
    era: 'ps1',
    eraEditPending: false,
  };

  it('is offered when unreviewed, launched, allowed, era known and no era edit pending', () => {
    expect(canOfferEraConfirm(offered)).toBe(true);
  });

  it.each(['confirmed', 'verified', undefined] as const)(
    'is hidden when era_review is %s',
    (eraReview) => {
      expect(canOfferEraConfirm({ ...offered, eraReview })).toBe(false);
    },
  );

  it.each([false, null, undefined] as const)('is hidden when has_launched is %s', (hasLaunched) => {
    expect(canOfferEraConfirm({ ...offered, hasLaunched })).toBe(false);
  });

  it('is hidden without permission to manage games', () => {
    expect(canOfferEraConfirm({ ...offered, canManageGame: false })).toBe(false);
  });

  it.each(['unknown', '', null, undefined] as const)('is hidden when era is %s', (era) => {
    expect(canOfferEraConfirm({ ...offered, era })).toBe(false);
  });

  it('is hidden while the form holds an unsaved era change', () => {
    expect(canOfferEraConfirm({ ...offered, eraEditPending: true })).toBe(false);
  });
});
