import { useEffect, useState } from 'react'

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
  environment_item_id : string
  profile_item_id: string
  executable_path: string
}

interface EditableItem {
  id: number
  cover_art_path: string | null
  executable_path: string | null
}

interface EditableCollection {
  title: string
  sort_title: string | null
  description: string | null
  publisher: string | null
  year: number | null
  category: string | null
  content_rating: string | null
  era: string
  environment_item_id : number | null
  profile_item_id: number | null
  launch_disk_id: number | null
  items: EditableItem[]
}

function formFromCollection(c: EditableCollection): EditForm {
  const launchDisc = c.items.find((i) => i.id === c.launch_disk_id) ?? c.items[0]
  return {
    title: c.title,
    sort_title: c.sort_title ?? '',
    description: c.description ?? '',
    publisher: c.publisher ?? '',
    year: c.year?.toString() ?? '',
    category: c.category ?? '',
    cover_art_path: launchDisc?.cover_art_path ?? '',
    content_rating: c.content_rating ?? '',
    era: c.era && c.era !== 'unknown' ? c.era : '',
    environment_item_id : c.environment_item_id ?.toString() ?? '',
    profile_item_id: c.profile_item_id?.toString() ?? '',
    executable_path: launchDisc?.executable_path ?? '',
  }
}

interface UseEditFormOptions<C extends EditableCollection> {
  collection: C | undefined
}

// Owns the edit-form field state for the collection detail page. Seeded once
// from the collection the first time it loads (never re-synced from a
// background refetch afterward) — callers reseed explicitly via
// resyncFromCollection(), e.g. after a save or a metadata-apply completes.
export function useEditForm<C extends EditableCollection>({ collection }: UseEditFormOptions<C>) {
  const [form, setFormState] = useState<EditForm | null>(null)

  useEffect(() => {
    if (collection && !form) {
      setFormState(formFromCollection(collection))
    }
  }, [collection, form])

  function setFormField<K extends keyof EditForm>(key: K, value: EditForm[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  function resyncFromCollection(fresh: C) {
    setFormState(formFromCollection(fresh))
  }

  return { form, setFormField, resyncFromCollection }
}
