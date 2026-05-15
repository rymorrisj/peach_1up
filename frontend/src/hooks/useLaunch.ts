import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useAppContext } from '@/context/AppContext'

type TargetType = 'library_item' | 'environment'

interface LaunchResult {
  launch_history_id: number
  warnings: string[]
}

interface LaunchOptions {
  profileId?: number | null
}

export interface UseLaunchReturn {
  launch: () => Promise<void>
  stop: () => Promise<void>
  isLaunching: boolean
  error: string | null
  warnings: string[]
}

export function useLaunch(
  targetId: number,
  targetType: TargetType,
  options?: LaunchOptions,
): UseLaunchReturn {
  const { state: appState } = useAppContext()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  const activeEntry = Array.from(appState.activeLaunches.values()).find(
    (e) => e.target_id === targetId && e.target_type === targetType && e.ended_at === null,
  )
  const isLaunching = activeEntry != null

  async function launch() {
    setError(null)
    setWarnings([])
    try {
      const endpoint =
        targetType === 'environment'
          ? `/api/v1/environments/${targetId}/launch`
          : `/api/v1/library/${targetId}/launch`
      const body: Record<string, unknown> = {}
      if (targetType === 'library_item' && options?.profileId != null) {
        body.profile_id = options.profileId
      }
      const res = await apiFetch<LaunchResult>(endpoint, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      setWarnings(res.warnings ?? [])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Launch failed.')
    }
  }

  async function stop() {
    if (!activeEntry?.launch_id) return
    try {
      await apiFetch(`/api/v1/launches/${activeEntry.launch_id}/stop`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['launches', targetType, targetId] })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Stop failed.')
    }
  }

  return { launch, stop, isLaunching, error, warnings }
}
