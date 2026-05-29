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
    era: item.era ?? '',
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

  const [form, setFormState] = useState<EditForm | null>(null)
  const [execBrowserOpen, setExecBrowserOpen] = useState(false)
  const [launchCommands, setLaunchCommands] = useState<string[] | null>(null)

  useEffect(() => {
    if (item && !form) setFormState(formFromItem(item))
  }, [item, form])

  useEffect(() => {
    if (item && launchCommands === null) {
      setLaunchCommands(item.launch_commands ?? [])
    }
  }, [item, launchCommands])

  function setField<K extends keyof EditForm>(key: K, value: EditForm[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  const saveMutation = useMutation<void, Error, { form: EditForm; launchCommands: string[] }>({
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

  function handleSave() {
    if (!form) return
    saveMutation.mutate({ form, launchCommands: launchCommands ?? item?.launch_commands ?? [] })
  }

  function handleSaveAdvanced() {
    if (!form) return
    saveMutation.mutate({ form, launchCommands: launchCommands ?? item?.launch_commands ?? [] })
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
    launchCommands,
    setLaunchCommands,
    handleSaveAdvanced,
  }
}
