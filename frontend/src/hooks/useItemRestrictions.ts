import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type LibraryItem = components['schemas']['LibraryItemRead']

interface UseItemRestrictionsOptions {
  item: LibraryItem | undefined
  isAdminOrOwner: boolean
  restrictionsData: { restricted_user_ids: number[] } | undefined
  refetchRestrictions: () => void
}

export function useItemRestrictions({
  item,
  isAdminOrOwner,
  restrictionsData,
  refetchRestrictions,
}: UseItemRestrictionsOptions) {
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
      if (!item) return Promise.resolve()
      return apiFetch(`/api/v1/library/${item.id}/restrictions`, {
        method: 'PUT',
        body: JSON.stringify({ user_ids: userIds }),
      })
    },
    onSuccess: () => {
      setRestrictionsDirty(false)
      queryClient.invalidateQueries({ queryKey: ['library'] })
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
