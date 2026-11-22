import { Button } from '@/ui';

interface ConfirmPlatformProps {
  onConfirm: () => void;
  pending: boolean;
  error: string | null;
}

// The "Confirm platform" action under the platform field. Visibility is decided by
// canOfferPlatformConfirm, this only renders it.
export function ConfirmPlatform({ onConfirm, pending, error }: ConfirmPlatformProps) {
  return (
    <div className="mt-2 space-y-1">
      <Button variant="primary" onClick={onConfirm} loading={pending}>
        Confirm platform
      </Button>
      <p className="text-xs text-fg-3">Only after you&apos;ve seen the game run correctly.</p>
      {error && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </div>
  );
}
