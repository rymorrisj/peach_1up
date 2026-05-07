import { cn } from '@/lib/utils'

type Status = 'ok' | 'missing' | 'error' | 'unknown'

interface StatusBadgeProps {
  status: string
  label?: string
}

const CONFIG: Record<Status, { classes: string; defaultLabel: string }> = {
  ok: {
    classes: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    defaultLabel: 'OK',
  },
  missing: {
    classes: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    defaultLabel: 'Missing',
  },
  error: {
    classes: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    defaultLabel: 'Error',
  },
  unknown: {
    classes: 'bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400',
    defaultLabel: 'Unknown',
  },
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const cfg = CONFIG[status as Status] ?? CONFIG.unknown
  return (
    <span className={cn('inline-flex rounded-full px-2 py-0.5 text-xs font-medium', cfg.classes)}>
      {label ?? cfg.defaultLabel}
    </span>
  )
}
