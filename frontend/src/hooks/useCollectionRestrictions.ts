import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

export type RestrictionDomain = 'game' | 'media' | 'app'

interface UseCollectionRestrictionsOptions {
  domain: RestrictionDomain
  collectionId: number | undefined
  isAdminOrOwner: boolean
  restrictionsData: { restricted_user_item_ids: number[] } | undefined
  refetchRestrictions: () => void
}

export function useCollectionRestrictions({
  domain,
  collectionId,
  isAdminOrOwner,
  restrictionsData,
  refetchRestrictions,
}: UseCollectionRestrictionsOptions) {
  const queryClient = useQueryClient()

  const [restrictedIds, setRestrictedIds] = useState<Set<number>>(new Set())
  const [restrictionsDirty, setRestrictionsDirty] = useState(false)

  useEffect(() => {
    if (restrictionsData && !restrictionsDirty) {
      setRestrictedIds(new Set(restrictionsData.restricted_user_item_ids))
    }
  }, [restrictionsData, restrictionsDirty])

  function toggleRestriction(userId: number) {
    setRestrictedIds((prev) => {
      const next = new Set(prev)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
    setRestrictionsDirty(true)
  }

  const saveMutation = useMutation<void, Error, number[]>({
    mutationFn: (userIds) => {
      if (!collectionId) return Promise.resolve()
      return apiFetch(`/api/v1/restrictions/${domain}/${collectionId}`, {
        method: 'PUT',
        body: JSON.stringify({ user_item_ids: userIds }),
      })
    },
    onSuccess: () => {
      setRestrictionsDirty(false)
      // Matches EntityListPage's own invalidate() key for this domain
      // (config.domain, 'list'). Was a hardcoded ['library'] key that only
      // ever matched the pre-cutover Games.tsx list query, so this was
      // already a no-op for Media/App (both already list under
      // [domain, 'list']) before this fix, and dead for Game too now that
      // Games.tsx has moved onto the same EntityListPage pattern.
      queryClient.invalidateQueries({ queryKey: [domain, 'list'] })
      refetchRestrictions()
    },
  })

  function handleSaveRestrictions() {
    if (!isAdminOrOwner) return
    saveMutation.mutate(Array.from(restrictedIds))
  }

  const savingRestrictions = saveMutation.isPending
  const restrictionsError = saveMutation.isError
    ? (saveMutation.error instanceof ApiError ? saveMutation.error.detail : 'Failed to save restrictions.')
    : null

  return {
    restrictedIds,
    restrictionsDirty,
    toggleRestriction,
    handleSaveRestrictions,
    savingRestrictions,
    restrictionsError,
  }
}
