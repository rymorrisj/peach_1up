import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useConfirm } from './useConfirm'

interface UseInstalledToggleOptions {
  collectionId: number | undefined
  detailQueryKey: unknown[]
  /** DOS: whether game files are already copied onto the drive, letting
   *  Peach 1UP skip the copy step and boot directly. PS3: whether the .pkg
   *  has already been installed into dev_hdd0/game/<TITLE_ID>/, letting
   *  Peach 1UP boot directly instead of running the RPCS3 installer.
   *  Defaults to 'dos' consequence copy for any other era. */
  era?: string
}

// Manual "installed" flag, shared by DOS (whether game files are already
// copied onto the drive) and PS3 (whether the .pkg is already installed
// into dev_hdd0/). Gated behind a confirm dialog since flipping it wrong
// causes either a stale-copy boot or an unwanted re-copy/re-install on next
// launch.
export function useInstalledToggle({ collectionId, detailQueryKey, era }: UseInstalledToggleOptions) {
  const queryClient = useQueryClient()
  const [localInstalled, setLocalInstalled] = useState(false)

  const {
    confirm,
    isOpen: confirmOpen,
    options: confirmOptions,
    handleConfirm,
    handleCancel,
  } = useConfirm()

  const installedMutation = useMutation<void, Error, boolean>({
    mutationFn: (value) => {
      if (collectionId == null) return Promise.resolve()
      return apiFetch(`/api/v1/game-item-bundle/${collectionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ installed: value }),
      })
    },
    onSuccess: (_, value) => {
      setLocalInstalled(value)
      queryClient.invalidateQueries({ queryKey: detailQueryKey })
    },
  })
  const installedError = installedMutation.isError
    ? (installedMutation.error instanceof ApiError ? installedMutation.error.detail : 'Failed to update.')
    : null

  async function handleToggleInstalled() {
    if (collectionId == null) return
    const target = !localInstalled
    const consequence = era === 'ps3'
      ? target
        ? 'Only confirm if this title is already installed into RPCS3 (dev_hdd0/game/). Peach 1UP will boot it directly instead of running the installer.'
        : 'This will re-run the RPCS3 installer on next launch. Peach 1UP re-detects an existing install from disk automatically, so this only matters if the install was removed outside of Peach 1UP.'
      : target
        ? 'Only confirm if your game files are already copied to this drive. Peach 1UP will skip the copy step and boot directly.'
        : 'This will re-run the copy step on next launch. Any changes made inside the drive will be preserved but source files will be copied again.'
    const confirmed = await confirm({
      title: target ? 'Mark as installed?' : 'Mark as not installed?',
      consequence,
      destructive: !target,
    })
    if (confirmed) installedMutation.mutate(target)
  }

  return {
    localInstalled,
    setLocalInstalled,
    handleToggleInstalled,
    isPending: installedMutation.isPending,
    installedError,
    confirmOpen,
    confirmOptions,
    handleConfirm,
    handleCancel,
  }
}
