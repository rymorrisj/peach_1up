import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

type VerificationStatus = 'verified' | 'caution' | 'not_in_index' | 'suspect' | 'unchecked'

interface VerifyGameCollectionResponse {
  verification_status: VerificationStatus
}

interface UseVerifyGameCollectionOptions {
  collectionId: number | undefined
  detailQueryKey: unknown[]
}

// On-demand re-check of every disc in a collection against the hash index,
// the manual counterpart to the verification_status ingest already writes
// automatically per disc (see backend/service/games/items.py's
// _prepare_item / _create_multi_disc_collection). Bundle-scoped rather than
// per-leaf, since a multi-disc game's true state is the worst state among
// all its discs, re-verifying only the launch disc would miss a bad disc 2.
export function useVerifyGameCollection({ collectionId, detailQueryKey }: UseVerifyGameCollectionOptions) {
  const queryClient = useQueryClient()
  const [verifying, setVerifying] = useState(false)
  const [verifyError, setVerifyError] = useState<string | null>(null)
  const [lastResultStatus, setLastResultStatus] = useState<VerificationStatus | null>(null)

  async function handleVerify() {
    if (collectionId == null) return
    setVerifying(true)
    setVerifyError(null)
    try {
      const result = await apiFetch<VerifyGameCollectionResponse>(
        `/api/v1/game-item-bundle/${collectionId}/verify`,
        { method: 'POST' },
      )
      setLastResultStatus(result.verification_status)
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    } catch (err) {
      setVerifyError(err instanceof ApiError ? err.detail : 'Failed to verify.')
    } finally {
      setVerifying(false)
    }
  }

  return { verifying, verifyError, lastResultStatus, handleVerify }
}
