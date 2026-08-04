import { cn } from '@/lib/utils';

type Status =
  | 'ok'
  | 'missing'
  | 'error'
  | 'unknown'
  | 'healthy'
  | 'degraded'
  | 'unconfigured'
  | 'verified'
  | 'caution'
  | 'not_in_index'
  | 'mismatch'
  | 'unchecked';

interface StatusBadgeProps {
  status: string;
  label?: string;
}

const CONFIG: Record<Status, { classes: string; defaultLabel: string }> = {
  ok: {
    classes: 'bg-success/15 text-success',
    defaultLabel: 'OK',
  },
  healthy: {
    classes: 'bg-success/15 text-success',
    defaultLabel: 'Healthy',
  },
  missing: {
    classes: 'bg-warning/15 text-warning',
    defaultLabel: 'Missing',
  },
  degraded: {
    classes: 'bg-warning/15 text-warning',
    defaultLabel: 'Degraded',
  },
  error: {
    classes: 'bg-error/15 text-error',
    defaultLabel: 'Error',
  },
  unknown: {
    classes: 'bg-info/15 text-info',
    defaultLabel: 'Unknown',
  },
  unconfigured: {
    classes: 'bg-info/15 text-info',
    defaultLabel: 'Unconfigured',
  },
  // Five-state hash verification model (backend: VerificationStatus in
  // backend/models/game.py). Placeholder treatment, exact icon/color choices
  // are not final, functional distinctness (5 visually different states) is
  // what matters right now.
  verified: {
    classes: 'bg-success/15 text-success',
    defaultLabel: '✓ Verified',
  },
  caution: {
    classes: 'bg-warning/15 text-warning',
    defaultLabel: '⚠ Caution',
  },
  not_in_index: {
    classes: 'bg-info/15 text-info',
    defaultLabel: 'Not in Index',
  },
  // Softer than error/red on purpose: a title-only match against an
  // inherently incomplete public hash catalog is expected to happen often
  // and is not itself a sign the file is bad (see _VERIFICATION_SEVERITY
  // in backend/models/game.py), grouped with caution's warning family
  // instead of the red "something is wrong" treatment the old "suspect"
  // name and styling implied.
  mismatch: {
    classes: 'bg-warning/15 text-warning',
    defaultLabel: 'Mismatch',
  },
  unchecked: {
    classes: 'bg-neutral-500/15 text-neutral-500',
    defaultLabel: 'Unchecked',
  },
};

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const cfg = CONFIG[status as Status] ?? CONFIG.unknown;
  return (
    <span className={cn('inline-flex rounded-full px-2 py-0.5 text-xs font-medium', cfg.classes)}>
      {label ?? cfg.defaultLabel}
    </span>
  );
}
