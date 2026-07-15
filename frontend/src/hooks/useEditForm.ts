import { useEffect, useState } from 'react'

interface UseEditFormOptions<C, F> {
  collection: C | undefined
  formFromCollection: (collection: C) => F
}

// Owns the edit-form field state for a collection detail page, domain-agnostic
// over the collection shape C and form shape F (each domain supplies its own
// formFromCollection). Seeded once from the collection the first time it
// loads (never re-synced from a background refetch afterward), callers
// reseed explicitly via resyncFromCollection(), e.g. after a save or a
// metadata-apply completes.
export function useEditForm<C, F>({ collection, formFromCollection }: UseEditFormOptions<C, F>) {
  const [form, setFormState] = useState<F | null>(null)

  useEffect(() => {
    if (collection && !form) {
      setFormState(formFromCollection(collection))
    }
  }, [collection, form, formFromCollection])

  function setFormField<K extends keyof F>(key: K, value: F[K]) {
    setFormState((prev) => prev && { ...prev, [key]: value })
  }

  function resyncFromCollection(fresh: C) {
    setFormState(formFromCollection(fresh))
  }

  return { form, setFormField, resyncFromCollection }
}
