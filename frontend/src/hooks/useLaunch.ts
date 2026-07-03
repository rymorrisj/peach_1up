import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type LaunchResponse = components['schemas']['LaunchResponse']

interface UseLaunchOptions {
  targetId: number
  targetType: string
  onSettled?: () => void
}

export function useLaunch({ targetId, targetType, onSettled }: UseLaunchOptions) {
  const [launchId, setLaunchId] = useState<number | null>(null)
  const [launchSuccess, setLaunchSuccess] = useState(false)
  const [launchWarnings, setLaunchWarnings] = useState<string[]>([])

  const onSettledRef = useRef(onSettled)
  useEffect(() => { onSettledRef.current = onSettled })

  useEffect(() => {
    if (!launchId) return
    const id = setInterval(async () => {
      try {
        const rec = await apiFetch<{ ended_at: string | null }>(`/api/v1/launches/${launchId}`)
        if (rec.ended_at != null) {
          setLaunchSuccess(false)
          setLaunchId(null)
          onSettledRef.current?.()
        }
      } catch {
        // poll errors are non-fatal
      }
    }, 2000)
    return () => clearInterval(id)
  }, [launchId])

  const launchMutation = useMutation<LaunchResponse, Error, number | null>({
    mutationFn: (profileId) => {
      // Two launch targets remain: an environment (platform) or a library
      // collection. A collection launch is keyed on the collection id.
      const path =
        targetType === 'environment'
          ? `/api/v1/environments/${targetId}/launch`
          : `/api/v1/library/${targetId}/launch`
      return apiFetch<LaunchResponse>(path, {
        method: 'POST',
        body: JSON.stringify({ profile_id: profileId }),
      })
    },
    onSuccess: (res) => {
      setLaunchId(res.launch_history_id)
      setLaunchWarnings(res.warnings)
      setLaunchSuccess(true)
    },
  })

  function launch(profileId: number | null = null) {
    setLaunchSuccess(false)
    setLaunchWarnings([])
    setLaunchId(null)
    launchMutation.mutate(profileId)
  }

  async function stop() {
    if (!launchId) return
    try {
      await apiFetch(`/api/v1/launches/${launchId}/stop`, { method: 'POST' })
    } catch (err) {
      console.error('Failed to stop launch:', err)
    } finally {
      setLaunchId(null)
    }
  }

  const isLaunching = launchMutation.isPending || launchId !== null
  const error = launchMutation.isError
    ? (launchMutation.error instanceof ApiError ? launchMutation.error.detail : 'Launch failed.')
    : null

  return { launch, stop, isLaunching, error, launchSuccess, launchWarnings }
}
