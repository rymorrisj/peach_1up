// Shared base for every Software domain's edit-form state. Fields are all
// string, matching the form-state convention (controlled input values), not
// the raw collection's nullable types.
export interface BaseSoftwareForm {
  title: string
  description: string
  cover_art_path: string
}
