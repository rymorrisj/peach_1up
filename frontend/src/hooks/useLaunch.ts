import { useEffect, useState } from 'react'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type LaunchResponse = components['schemas']['LaunchResponse']

export function useLaunch(targetId: number, targetType: string) {
  const [isLaunching, setIsLaunching] = useState(false)
  const [launchId, setLaunchId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  useEffect(() => {
    if (!launchId) return
    const id = setInterval(async () => {
      try {
        const rec = await apiFetch<{ ended_at: string | null }>(`/api/v1/launches/${launchId}`)
        if (rec.ended_at != null) {
          setIsLaunching(false)
          setLaunchId(null)
        }
      } catch {
        // poll errors are non-fatal
      }
    }, 3000)
    return () => clearInterval(id)
  }, [launchId])

  async function launch() {
    setIsLaunching(true)
    setError(null)
    setWarnings([])
    try {
      const path =
        targetType === 'environment'
          ? `/api/v1/environments/${targetId}/launch`
          : `/api/v1/library/${targetId}/launch`
      const res = await apiFetch<LaunchResponse>(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: null }),
      })
      setLaunchId(res.launch_history_id)
      setWarnings(res.warnings)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Launch failed.')
      setIsLaunching(false)
    }
  }

  async function stop() {
    if (!launchId) return
    try {
      await apiFetch(`/api/v1/launches/${launchId}/stop`, { method: 'POST' })
    } catch {
      // ignore
    } finally {
      setIsLaunching(false)
      setLaunchId(null)
    }
  }

  return { launch, stop, isLaunching, error, warnings }
}
