import { StatusBadge } from '@/ui'

const STATUS_TO_BADGE: Record<string, string> = {
  ok: 'ok',
  healthy: 'ok',
  missing: 'missing',
  degraded: 'missing',
  unknown: 'missing',
  error: 'error',
}

const STATUS_LABELS: Record<string, string> = {
  ok: 'Healthy',
  healthy: 'Healthy',
  missing: 'Missing',
  degraded: 'Degraded',
  unknown: 'Unknown',
  error: 'Error',
}

interface HealthStatusProps {
  status: string
}

export default function HealthStatus({ status }: HealthStatusProps) {
  const badge = STATUS_TO_BADGE[status] ?? 'unknown'
  const label = STATUS_LABELS[status] ?? status
  return <StatusBadge status={badge} label={label} />
}
