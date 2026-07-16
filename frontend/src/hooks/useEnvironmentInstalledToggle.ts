import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useConfirm } from './useConfirm'

interface UseEnvironmentInstalledToggleOptions {
  environmentId: number | undefined
}

// Win9x/WinXp "OS installed" flag: whether the user has finished running the
// installer inside this Environment. Same interaction shape as
// useInstalledToggle (DOS game-files-copied flag) -- confirm dialog first,
// since environment_is_installed() (era_defaults.py) now gates launch
// eligibility on this value, so flipping it wrong hides a real Environment
// from PlatformField or marks an unfinished install as ready.
export function useEnvironmentInstalledToggle({ environmentId }: UseEnvironmentInstalledToggleOptions) {
  const queryClient = useQueryClient()

  const {
    confirm,
    isOpen: confirmOpen,
    options: confirmOptions,
    handleConfirm,
    handleCancel,
  } = useConfirm()

  const installedMutation = useMutation<void, Error, boolean>({
    mutationFn: (value) => {
      if (environmentId == null) return Promise.resolve()
      return apiFetch(`/api/v1/environment-items/${environmentId}`, {
        method: 'PATCH',
        body: JSON.stringify({ installed_at: value ? new Date().toISOString() : null }),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['platforms'] })
      queryClient.invalidateQueries({ queryKey: ['platform', environmentId] })
    },
  })
  const installedError = installedMutation.isError
    ? (installedMutation.error instanceof ApiError ? installedMutation.error.detail : 'Failed to update.')
    : null

  async function handleToggleInstalled(currentlyInstalled: boolean) {
    if (environmentId == null) return
    const target = !currentlyInstalled
    const consequence = target
      ? 'Only confirm if you have finished running the OS installer inside this Environment.'
      : 'This marks the Environment as not yet installed -- it will show as unlaunchable until marked installed again.'
    const confirmed = await confirm({
      title: target ? 'Mark as installed?' : 'Mark as not installed?',
      consequence,
      destructive: !target,
    })
    if (confirmed) installedMutation.mutate(target)
  }

  return {
    handleToggleInstalled,
    isPending: installedMutation.isPending,
    installedError,
    confirmOpen,
    confirmOptions,
    handleConfirm,
    handleCancel,
  }
}
