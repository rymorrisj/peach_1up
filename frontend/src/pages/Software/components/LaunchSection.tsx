import type { ReactNode } from 'react';
import { Button } from '@/ui';

interface LaunchSectionProps {
  onLaunch: () => void;
  launching?: boolean;
  launchDisabled?: boolean;
  launchButtonLabel?: string;
  /** Note rendered directly below the launch button */
  launchNote?: ReactNode;
  launchSuccess?: boolean;
  launchWarnings?: string[];
  launchError?: string | null;
  /** Rendered directly below the launch error (e.g. a "Convert with extract-xiso" action) */
  launchErrorAction?: ReactNode;
}

// Callers only render this when they have an onLaunch handler, see the
// {onLaunch && <LaunchSection .../>} guard in SoftwareEntityDetail.
export function LaunchSection({
  onLaunch,
  launching,
  launchDisabled,
  launchButtonLabel = 'Launch',
  launchNote,
  launchSuccess,
  launchWarnings,
  launchError,
  launchErrorAction,
}: LaunchSectionProps) {
  return (
    <section className="space-y-2">
      <div className="flex justify-center">
        <Button
          onClick={onLaunch}
          loading={!!launching}
          disabled={launchDisabled ?? !!launching}
          className="px-10 py-3 text-base"
        >
          {launchButtonLabel}
        </Button>
      </div>

      {launchNote}

      {launchSuccess && (
        <p className="text-center text-sm text-green-600 dark:text-green-400">
          Launch started. The emulator should open shortly.
        </p>
      )}

      {(launchWarnings ?? []).map((w, i) => (
        <p key={i} className="text-center text-xs text-amber-600 dark:text-amber-400">
          ⚠ {w}
        </p>
      ))}

      {launchError && (
        <p role="alert" className="text-center text-sm text-red-600 dark:text-red-400">
          ❌ {launchError}
        </p>
      )}

      {launchError && launchErrorAction}
    </section>
  );
}
