import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { apiFetch, ApiError, TimeoutError } from '@/api/client';

// Server-side launch dispatch alone is capped at 30s (see coordinator.py
// _LAUNCH_TIMEOUT); first-time environment provisioning (VM creation, drive
// setup) runs before that and is unbounded, so give the browser real margin
// before it gives up and mislabels an in-flight launch as failed.
export const LAUNCH_TIMEOUT_MS = 45_000;
import type { components } from '@shared/types';

type LaunchResponse = components['schemas']['LaunchResponse'];

type LaunchTargetType = 'game_item_bundle' | 'app' | 'environment';

const LAUNCH_PATH: Record<LaunchTargetType, (id: number) => string> = {
  game_item_bundle: (id) => `/api/v1/game-item-bundle/${id}/launch`,
  app: (id) => `/api/v1/app-item-bundle/${id}/launch`,
  environment: (id) => `/api/v1/environment-items/${id}/launch`,
};

interface UseLaunchOptions {
  targetId: number;
  targetType: LaunchTargetType;
  onSettled?: () => void;
}

export function useLaunch({ targetId, targetType, onSettled }: UseLaunchOptions) {
  const [launchId, setLaunchId] = useState<number | null>(null);
  const [launchSuccess, setLaunchSuccess] = useState(false);
  const [launchWarnings, setLaunchWarnings] = useState<string[]>([]);

  const onSettledRef = useRef(onSettled);
  useEffect(() => {
    onSettledRef.current = onSettled;
  });

  useEffect(() => {
    if (!launchId) return;
    const id = setInterval(async () => {
      try {
        const rec = await apiFetch<{ ended_at: string | null }>(`/api/v1/launches/${launchId}`);
        if (rec.ended_at != null) {
          setLaunchSuccess(false);
          setLaunchId(null);
          onSettledRef.current?.();
        }
      } catch {
        // poll errors are non-fatal
      }
    }, 2000);
    return () => clearInterval(id);
  }, [launchId]);

  const launchMutation = useMutation<LaunchResponse, Error, number | null>({
    mutationFn: (profileId) => {
      const buildPath = LAUNCH_PATH[targetType];
      if (!buildPath) throw new Error(`useLaunch: unhandled targetType "${targetType}"`);
      return apiFetch<LaunchResponse>(buildPath(targetId), {
        method: 'POST',
        body: JSON.stringify({ profile_item_id: profileId }),
        timeoutMs: LAUNCH_TIMEOUT_MS,
      });
    },
    onSuccess: (res) => {
      setLaunchId(res.launch_history_id);
      setLaunchWarnings(res.warnings);
      setLaunchSuccess(true);
    },
  });

  function launch(profileId: number | null = null) {
    setLaunchSuccess(false);
    setLaunchWarnings([]);
    setLaunchId(null);
    launchMutation.mutate(profileId);
  }

  async function stop() {
    if (!launchId) return;
    try {
      await apiFetch(`/api/v1/launches/${launchId}/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop launch:', err);
    } finally {
      setLaunchId(null);
    }
  }

  const isLaunching = launchMutation.isPending || launchId !== null;
  const apiError = launchMutation.error instanceof ApiError ? launchMutation.error : null;
  const error = launchMutation.isError
    ? apiError
      ? apiError.detail
      : launchMutation.error instanceof TimeoutError
        ? 'Launch is taking longer than expected — check if it opened.'
        : 'Launch failed.'
    : null;
  // Structured detail set by specific failure shapes (e.g. coordinator.py's
  // XboxDvdRipDetected branch) so callers can offer a targeted fix instead of
  // just showing the message — undefined for every ordinary launch failure.
  const errorType =
    apiError && typeof apiError.rawDetail === 'object' && apiError.rawDetail !== null
      ? (apiError.rawDetail as { error_type?: string }).error_type
      : undefined;

  return { launch, stop, isLaunching, error, errorType, launchSuccess, launchWarnings };
}
