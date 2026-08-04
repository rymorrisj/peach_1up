const OK_STATUSES = new Set([
  'ok',
  'healthy',
  'detected',
  'installed',
  'installer ready',
  'present',
  'complete',
]);

const ERROR_STATUSES = new Set(['error', 'missing']);

const STATUS_LABELS: Record<string, string> = {
  ok: 'Healthy',
  healthy: 'Healthy',
  missing: 'Missing',
  error: 'Error',
  degraded: 'Degraded',
  unconfigured: 'Unconfigured',
  unknown: 'Unknown',
};

interface EmulatorStatusProps {
  status: string;
}

export default function EmulatorStatus({ status }: EmulatorStatusProps) {
  const key = (status ?? '').toLowerCase();
  const label = STATUS_LABELS[key] ?? status;

  let colorClass: string;
  let icon: string;
  if (OK_STATUSES.has(key)) {
    colorClass = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    icon = '✓';
  } else if (ERROR_STATUSES.has(key)) {
    colorClass = 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
    icon = '✗';
  } else {
    colorClass = 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400';
    icon = '!';
  }

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClass}`}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}
