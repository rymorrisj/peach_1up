import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { apiFetch, ApiError, TimeoutError } from '@/api/client';

// Server-side launch dispatch alone is capped at 30s (see coordinator.py
// _LAUNCH_TIMEOUT); first-time environment provisioning (VM creation, drive
// setup) runs before that and is unbounded, so give the browser real margin
// before it gives up and mislabels an in-flight launch as failed.
export const LAUNCH_TIMEOUT_MS = 45_000;
import type { components } from '@shared/types';

const POLL_INTERVAL_MS = 2000;
// The poll tracks the running game until its process ends, so it has no
// attempt cap. Only consecutive poll failures stop it.
const MAX_POLL_FAILURES = 5;

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
  const [pollError, setPollError] = useState<string | null>(null);

  const onSettledRef = useRef(onSettled);
  useEffect(() => {
    onSettledRef.current = onSettled;
  });

  useEffect(() => {
    if (!launchId) return;
    let failures = 0;
    let cancelled = false;
    const giveUp = (message: string) => {
      clearInterval(id);
      setLaunchSuccess(false);
      setLaunchId(null);
      setPollError(message);
    };
    const id = setInterval(async () => {
      try {
        const rec = await apiFetch<{ ended_at: string | null }>(`/api/v1/launches/${launchId}`);
        if (cancelled) return;
        failures = 0;
        if (rec.ended_at != null) {
          clearInterval(id);
          setLaunchSuccess(false);
          setLaunchId(null);
          onSettledRef.current?.();
        }
      } catch (err) {
        if (cancelled) return;
        console.error('Launch status poll failed:', err);
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          giveUp(
            err instanceof ApiError
              ? `Lost track of the launch: ${err.detail}`
              : 'Lost contact with the server while checking the launch.',
          );
        }
      }
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
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
    setPollError(null);
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
  const mutationError = launchMutation.isError
    ? apiError
      ? apiError.detail
      : launchMutation.error instanceof TimeoutError
        ? 'Launch is taking longer than expected, check if it opened.'
        : 'Launch failed.'
    : null;
  const error = pollError ?? mutationError;
  // Structured detail set by specific failure shapes (e.g. coordinator.py's
  // XboxDvdRipDetected branch) so callers can offer a targeted fix instead of
  // just showing the message, undefined for every ordinary launch failure.
  const errorType =
    apiError && typeof apiError.rawDetail === 'object' && apiError.rawDetail !== null
      ? (apiError.rawDetail as { error_type?: string }).error_type
      : undefined;

  return { launch, stop, isLaunching, error, errorType, launchSuccess, launchWarnings };
}
