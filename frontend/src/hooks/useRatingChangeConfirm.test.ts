import { renderHook, act } from '@testing-library/react';
import { ApiError } from '@/api/client';
import {
  RATING_CHANGE_ERROR_TYPE,
  ratingChangeAffectedCount,
  ratingChangeMessage,
  useRatingChangeConfirm,
} from '@/hooks/useRatingChangeConfirm';

function ratingConflict(count: number): ApiError {
  return new ApiError(409, 'loosens a rating', {
    error_type: RATING_CHANGE_ERROR_TYPE,
    message: 'loosens a rating',
    affected_count: count,
  });
}

describe('ratingChangeAffectedCount', () => {
  it('reads affected_count from a rating-change 409', () => {
    expect(ratingChangeAffectedCount(ratingConflict(3))).toBe(3);
  });

  it('returns null for other errors', () => {
    expect(
      ratingChangeAffectedCount(new ApiError(409, 'conflict', 'A plain string detail')),
    ).toBeNull();
    expect(
      ratingChangeAffectedCount(
        new ApiError(409, 'x', { error_type: 'something_else', message: 'x' }),
      ),
    ).toBeNull();
    expect(
      ratingChangeAffectedCount(
        new ApiError(400, 'x', { error_type: RATING_CHANGE_ERROR_TYPE, affected_count: 1 }),
      ),
    ).toBeNull();
    expect(ratingChangeAffectedCount(new Error('network'))).toBeNull();
  });
});

describe('ratingChangeMessage', () => {
  it('pluralises the item count', () => {
    expect(ratingChangeMessage(1)).toBe('This changes who can see 1 media item. Continue?');
    expect(ratingChangeMessage(4)).toBe('This changes who can see 4 media items. Continue?');
  });
});

describe('useRatingChangeConfirm', () => {
  it('runs once without prompting when the action succeeds', async () => {
    const confirm = vi.fn();
    const run = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useRatingChangeConfirm(confirm));

    let completed!: boolean;
    await act(async () => {
      completed = await result.current(run);
    });

    expect(completed).toBe(true);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith(false);
    expect(confirm).not.toHaveBeenCalled();
  });

  it('prompts on a rating-change 409 and retries with the flag when confirmed', async () => {
    const confirm = vi.fn().mockResolvedValue(true);
    const run = vi.fn().mockRejectedValueOnce(ratingConflict(2)).mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useRatingChangeConfirm(confirm));

    let completed!: boolean;
    await act(async () => {
      completed = await result.current(run);
    });

    expect(completed).toBe(true);
    expect(confirm).toHaveBeenCalledWith(
      expect.objectContaining({ consequence: 'This changes who can see 2 media items. Continue?' }),
    );
    expect(run.mock.calls).toEqual([[false], [true]]);
  });

  it('does not retry when the prompt is cancelled', async () => {
    const confirm = vi.fn().mockResolvedValue(false);
    const run = vi.fn().mockRejectedValueOnce(ratingConflict(1));
    const { result } = renderHook(() => useRatingChangeConfirm(confirm));

    let completed!: boolean;
    await act(async () => {
      completed = await result.current(run);
    });

    expect(completed).toBe(false);
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('propagates any other error without prompting', async () => {
    const confirm = vi.fn();
    const run = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(400, 'Invalid or expired confirmation token.'));
    const { result } = renderHook(() => useRatingChangeConfirm(confirm));

    await expect(
      act(async () => {
        await result.current(run);
      }),
    ).rejects.toMatchObject({ status: 400 });
    expect(confirm).not.toHaveBeenCalled();
  });

  it('propagates an error from the confirmed retry', async () => {
    const confirm = vi.fn().mockResolvedValue(true);
    const run = vi
      .fn()
      .mockRejectedValueOnce(ratingConflict(1))
      .mockRejectedValueOnce(new ApiError(500, 'boom'));
    const { result } = renderHook(() => useRatingChangeConfirm(confirm));

    await expect(
      act(async () => {
        await result.current(run);
      }),
    ).rejects.toMatchObject({ status: 500 });
    expect(run).toHaveBeenCalledTimes(2);
  });
});
