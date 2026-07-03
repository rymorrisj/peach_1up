import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type LibraryItem = components['schemas']['LibraryItemRead']

export interface EditForm {
  title: string
  sort_title: string
  description: string
  publisher: string
  year: string
  category: string
  cover_art_path: string
  content_rating: string
  era: string
  platform_id: string
  profile_id: string
  executable_path: string
}

export function formFromItem(item: LibraryItem): EditForm {
  return {
    title: item.title,
    sort_title: item.sort_title ?? '',
    description: item.description ?? '',
    publisher: item.publisher ?? '',
    year: item.year?.toString() ?? '',
    category: item.category ?? '',
    cover_art_path: item.cover_art_path ?? '',
    content_rating: item.content_rating ?? '',
    era: (item.era && item.era !== 'unknown') ? item.era : '',
    platform_id: item.platform_id?.toString() ?? '',
    profile_id: item.profile_id?.toString() ?? '',
    executable_path: item.executable_path ?? '',
  }
}

interface UseEditFormOptions {
  item: LibraryItem | undefined
  slug: string | undefined
}

export function useEditForm({ item, slug }: UseEditFormOptions) {
  const queryClient = useQueryClient()

  const [form, setFormState] = useState<EditForm | null>(() => item ? formFromItem(item) : null)
  const [execBrowserOpen, setExecBrowserOpen] = useState(false)
  // undefined = not yet loaded; null = never configured (preserve, media may
  // auto-run); [] = explicitly cleared (persist as empty → no auto-run).
  // Using undefined as the load sentinel keeps null distinguishable from [].
  const [launchCommands, setLaunchCommands] = useState<string[] | null | undefined>(
    () => item ? (item.launch_commands ?? null) : undefined,
  )

  // Seed/reset form when item loads or when navigating between items.
  useEffect(() => {
    if (item) {
      setFormState(formFromItem(item))
      setLaunchCommands(item.launch_commands ?? null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.id])

  function setField<K extends keyof EditForm>(key: K, value: EditForm[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  const saveMutation = useMutation<void, Error, { form: EditForm; launchCommands: string[] | null }>({
    mutationFn: async ({ form: f, launchCommands: cmds }) => {
      if (!item) return
      await apiFetch(`/api/v1/library/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: f.title.trim() || undefined,
          sort_title: f.sort_title.trim() || null,
          description: f.description.trim() || null,
          publisher: f.publisher.trim() || null,
          year: f.year ? parseInt(f.year, 10) : null,
          category: f.category.trim() || null,
          cover_art_path: f.cover_art_path.trim() || null,
          content_rating: f.content_rating || null,
          era: f.era || null,
          platform_id: f.platform_id ? parseInt(f.platform_id, 10) : null,
          profile_id: f.profile_id ? parseInt(f.profile_id, 10) : null,
          executable_path: f.executable_path.trim() || null,
          launch_commands: cmds,
        }),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library'] })
      queryClient.invalidateQueries({ queryKey: ['library', 'by-slug', slug] })
    },
  })

  // Send state verbatim so [] (cleared) and null (unset) are preserved. null is
  // dropped server-side (exclude_none), leaving the stored value untouched — so
  // an incidental save without touching commands can't flip null → [].
  function resolveLaunchCommands(): string[] | null {
    return launchCommands === undefined ? (item?.launch_commands ?? null) : launchCommands
  }

  function handleSave() {
    if (!form) return
    saveMutation.mutate({ form, launchCommands: resolveLaunchCommands() })
  }

  const saving = saveMutation.isPending
  const saveError = saveMutation.isError
    ? (saveMutation.error instanceof ApiError ? saveMutation.error.detail : 'Failed to save.')
    : null
  const saveSuccess = saveMutation.isSuccess

  return {
    form,
    setField,
    handleSave,
    saving,
    saveError,
    saveSuccess,
    execBrowserOpen,
    setExecBrowserOpen,
    launchCommands: launchCommands ?? null,
    setLaunchCommands,
  }
}
