import type { BaseSoftwareForm } from './softwareForm';

export interface SoftwareMediaForm extends BaseSoftwareForm {
  // Own rating, edited only while the bundle has no linked software ('' is
  // unrated). A linked bundle inherits its rating and never sends this.
  content_rating: string;
}

export interface EditableMediaCollection {
  title: string;
  description: string | null;
  cover_art_path: string | null;
  content_rating: string | null;
}

// Simpler than Game's/App's: cover_art_path lives directly on the bundle
// (confirmed against backend/models/media.py's MediaItemBundle), no
// launch-disc leaf traversal needed.
export function formFromCollection(c: EditableMediaCollection): SoftwareMediaForm {
  return {
    title: c.title,
    description: c.description ?? '',
    cover_art_path: c.cover_art_path ?? '',
    content_rating: c.content_rating ?? '',
  };
}
