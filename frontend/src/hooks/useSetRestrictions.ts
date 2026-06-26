import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

interface UseSetRestrictionsOptions {
  setId: number | undefined
  isAdminOrOwner: boolean
  restrictionsData: { restricted_user_ids: number[] } | undefined
  refetchRestrictions: () => void
}

export function useSetRestrictions({
  setId,
  isAdminOrOwner,
  restrictionsData,
  refetchRestrictions,
}: UseSetRestrictionsOptions) {
  const queryClient = useQueryClient()

  const [restrictedIds, setRestrictedIds] = useState<Set<number>>(new Set())
  const [restrictionsDirty, setRestrictionsDirty] = useState(false)

  useEffect(() => {
    if (restrictionsData && !restrictionsDirty) {
      setRestrictedIds(new Set(restrictionsData.restricted_user_ids))
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
      if (!setId) return Promise.resolve()
      return apiFetch(`/api/v1/library/sets/${setId}/restrictions`, {
        method: 'PUT',
        body: JSON.stringify({ user_ids: userIds }),
      })
    },
    onSuccess: () => {
      setRestrictionsDirty(false)
      queryClient.invalidateQueries({ queryKey: ['library', 'sets'] })
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
