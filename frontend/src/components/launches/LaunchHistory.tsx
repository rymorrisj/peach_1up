import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

type LaunchHistoryRead = components['schemas']['LaunchHistoryRead']

interface LaunchHistoryProps {
  targetId: number
  targetType: string
}

export default function LaunchHistory({ targetId, targetType }: LaunchHistoryProps) {
  const { data: launches } = useQuery<LaunchHistoryRead[]>({
    queryKey: ['launches', targetType, targetId],
    queryFn: () =>
      apiFetch<LaunchHistoryRead[]>(
        `/api/v1/launches?target_id=${targetId}&target_type=${targetType}`,
      ),
  })

  if (!launches || launches.length === 0) return null

  return (
    <div className="mt-2 border-t border-neutral-100 pt-2 dark:border-neutral-800">
      {launches.slice(0, 5).map((l) => (
        <div key={l.id} className="flex items-center gap-2 py-0.5 text-xs text-neutral-400">
          <span>{new Date(l.started_at + 'Z').toLocaleString()}</span>
          {l.ended_at ? (
            <span>{new Date(l.ended_at + 'Z').toLocaleString()}</span>
          ) : (
            <span className="text-green-500">running</span>
          )}
        </div>
      ))}
    </div>
  )
}
