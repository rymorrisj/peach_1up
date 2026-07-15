import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

interface UseFlagLaunchOptions {
  collectionId: number | undefined
  detailQueryKey: unknown[]
}

export function useFlagLaunch({ collectionId, detailQueryKey }: UseFlagLaunchOptions) {
  const queryClient = useQueryClient()
  const [flagging, setFlagging] = useState(false)
  const [flagError, setFlagError] = useState<string | null>(null)

  async function handleFlagLaunch() {
    if (collectionId == null) return
    setFlagging(true)
    setFlagError(null)
    try {
      await apiFetch(`/api/v1/game-item-bundle/${collectionId}/flag-launch`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    } catch (err) {
      setFlagError(err instanceof ApiError ? err.detail : 'Failed to flag.')
    } finally {
      setFlagging(false)
    }
  }

  return { flagging, flagError, handleFlagLaunch }
}
