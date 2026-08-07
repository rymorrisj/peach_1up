import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useLaunch } from '@/hooks/useLaunch';
import { apiFetch } from '@/api/client';

vi.mock('@/api/client', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/api/client')>();
  return { ...mod, apiFetch: vi.fn() };
});

const mockApiFetch = vi.mocked(apiFetch);

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useLaunch', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.useRealTimers());

  it('launch() sends POST to the game-item-bundle endpoint with the given profileId', async () => {
    mockApiFetch.mockResolvedValueOnce({ launch_history_id: 1, warnings: [] });

    const { result } = renderHook(() => useLaunch({ targetId: 7, targetType: 'collection' }), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.launch(3);
    });

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/game-item-bundle/7/launch',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ profile_item_id: 3 }),
      }),
    );
  });

  it('launch() sends POST to the app-item-bundle endpoint for targetType "app"', async () => {
    mockApiFetch.mockResolvedValueOnce({ launch_history_id: 2, warnings: [] });

    const { result } = renderHook(() => useLaunch({ targetId: 9, targetType: 'app' }), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.launch(null);
    });

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/app-item-bundle/9/launch',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ profile_item_id: null }),
      }),
    );
  });

  it('launchWarnings is populated from the launch response', async () => {
    mockApiFetch.mockResolvedValueOnce({
      launch_history_id: 1,
      warnings: ['low memory', 'no BIOS'],
    });

    const { result } = renderHook(() => useLaunch({ targetId: 1, targetType: 'collection' }), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.launch(null);
    });

    await waitFor(() => expect(result.current.launchWarnings).toEqual(['low memory', 'no BIOS']));
  });

  it('polling stops and launchSuccess clears when ended_at becomes non-null', async () => {
    vi.useFakeTimers();

    mockApiFetch
      .mockResolvedValueOnce({ launch_history_id: 42, warnings: [] })
      .mockResolvedValueOnce({ ended_at: '2024-01-01T00:00:00Z' });

    const { result } = renderHook(() => useLaunch({ targetId: 1, targetType: 'collection' }), {
      wrapper: createWrapper(),
    });

    // Flush mutation onSuccess, two act rounds drain TanStack's scheduler
    await act(async () => {
      result.current.launch(null);
    });
    await act(async () => {});

    // Advance fake clock wrapped in act so React commits the state updates
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(result.current.launchSuccess).toBe(false);
  });

  it('onSettled callback fires when the poll detects ended_at', async () => {
    vi.useFakeTimers();

    const onSettled = vi.fn();
    mockApiFetch
      .mockResolvedValueOnce({ launch_history_id: 99, warnings: [] })
      .mockResolvedValueOnce({ ended_at: '2024-01-01T00:00:00Z' });

    const { result } = renderHook(
      () => useLaunch({ targetId: 1, targetType: 'collection', onSettled }),
      { wrapper: createWrapper() },
    );

    // Flush mutation onSuccess, two act rounds drain TanStack's scheduler
    await act(async () => {
      result.current.launch(null);
    });
    await act(async () => {});

    // Advance fake clock wrapped in act so React commits the state updates
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(onSettled).toHaveBeenCalledOnce();
  });
});
