import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useEditForm } from '@/hooks/useEditForm'
import { useItemRestrictions } from '@/hooks/useItemRestrictions'
import { useConfirm } from '@/hooks/useConfirm'
import type { components } from '@shared/types'

type LibraryItem = components['schemas']['LibraryItemRead']

interface UseLibraryItemActionsOptions {
  item: LibraryItem | undefined
  slug: string | undefined
  isAdminOrOwner: boolean
  restrictionsData: { restricted_user_ids: number[] } | undefined
  refetchRestrictions: () => void
}

export function useLibraryItemActions({
  item,
  slug,
  isAdminOrOwner,
  restrictionsData,
  refetchRestrictions,
}: UseLibraryItemActionsOptions) {
  const queryClient = useQueryClient()

  const editForm = useEditForm({ item, slug })

  const restrictions = useItemRestrictions({
    item,
    isAdminOrOwner,
    restrictionsData,
    refetchRestrictions,
  })

  const [flagging, setFlagging] = useState(false)
  const [flagError, setFlagError] = useState<string | null>(null)

  async function handleFlagLaunch() {
    if (!item) return
    setFlagging(true)
    setFlagError(null)
    try {
      await apiFetch(`/api/v1/library/${item.id}/flag-launch`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setFlagError(err instanceof ApiError ? err.detail : 'Failed to flag.')
    } finally {
      setFlagging(false)
    }
  }

  const [tagError, setTagError] = useState<string | null>(null)

  async function handleRemoveTag(tagId: number) {
    if (!item) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/items/${item.id}`, { method: 'DELETE' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to remove tag.')
    }
  }

  async function handleAssignTag(tagId: number) {
    if (!item) return
    setTagError(null)
    try {
      await apiFetch(`/api/v1/tags/${tagId}/items/${item.id}`, { method: 'POST' })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    } catch (err) {
      setTagError(err instanceof ApiError ? err.detail : 'Failed to add tag.')
    }
  }

  const [localInstalled, setLocalInstalled] = useState(false)

  useEffect(() => {
    if (item) setLocalInstalled(item.installed)
  }, [item])

  const {
    confirm: confirmInstalled,
    isOpen: installedConfirmOpen,
    options: installedConfirmOptions,
    handleConfirm: handleInstalledConfirm,
    handleCancel: handleInstalledCancel,
  } = useConfirm()

  const installedMutation = useMutation<void, Error, boolean>({
    mutationFn: (value) => {
      if (!item) return Promise.resolve()
      return apiFetch(`/api/v1/library/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ installed: value }),
      })
    },
    onSuccess: (_, value) => {
      setLocalInstalled(value)
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    },
  })

  async function handleToggleInstalled() {
    if (!item) return
    const target = !localInstalled
    const consequence = target
      ? 'Only confirm if your game files are already copied to this drive. Peach 1UP will skip the copy step and boot directly.'
      : 'This will re-run the copy step on next launch. Any changes made inside the drive will be preserved but source files will be copied again.'
    const confirmed = await confirmInstalled({
      title: target ? 'Mark as installed?' : 'Mark as not installed?',
      consequence,
      destructive: !target,
    })
    if (confirmed) installedMutation.mutate(target)
  }

  return {
    ...editForm,
    ...restrictions,
    flagging,
    flagError,
    handleFlagLaunch,
    tagError,
    handleRemoveTag,
    handleAssignTag,
    localInstalled,
    handleToggleInstalled,
    installedMutation,
    installedConfirmOpen,
    installedConfirmOptions,
    handleInstalledConfirm,
    handleInstalledCancel,
  }
}
