// Shared edit-form field shape for the collection detail page and the EditForm
// component. The item-only useEditForm hook / formFromItem builder were removed
// in the collection consolidation — the collection detail page owns its own
// form-from-collection builder and save mutation.

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
