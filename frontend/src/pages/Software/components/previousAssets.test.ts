import { ApiError } from '@/api/client';
import { PREVIOUS_ASSETS_ERROR_TYPE, previousAssetsCount } from './previousAssets';

describe('previousAssetsCount', () => {
  it('reads existing_count from the structured 409', () => {
    const err = new ApiError(409, 'x', {
      error_type: PREVIOUS_ASSETS_ERROR_TYPE,
      existing_count: 4,
    });
    expect(previousAssetsCount(err)).toBe(4);
  });

  it('ignores other 409s and other errors', () => {
    expect(
      previousAssetsCount(new ApiError(409, 'An Accept All for this game is already running.')),
    ).toBeNull();
    expect(
      previousAssetsCount(new ApiError(422, 'x', { error_type: PREVIOUS_ASSETS_ERROR_TYPE })),
    ).toBeNull();
    expect(previousAssetsCount(new Error('network'))).toBeNull();
  });
});
