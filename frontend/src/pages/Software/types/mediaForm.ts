import type { BaseSoftwareForm } from './softwareForm'

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface SoftwareMediaForm extends BaseSoftwareForm {}

export interface EditableMediaCollection {
  title: string
  description: string | null
  cover_art_path: string | null
}

// Simpler than Game's/App's: cover_art_path lives directly on the bundle
// (confirmed against backend/models/media.py's MediaItemBundle), no
// launch-disc leaf traversal needed.
export function formFromCollection(c: EditableMediaCollection): SoftwareMediaForm {
  return {
    title: c.title,
    description: c.description ?? '',
    cover_art_path: c.cover_art_path ?? '',
  }
}
