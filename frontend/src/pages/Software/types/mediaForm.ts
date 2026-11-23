import type { BaseSoftwareForm } from './softwareForm';

// No cover_art_path: a media cover is chosen from the bundle's own files
// (FilesSection), never typed or browsed, so media-only editors need no
// filesystem browse access.
export interface SoftwareMediaForm extends Omit<BaseSoftwareForm, 'cover_art_path'> {
  // Own rating, edited only while the bundle has no linked software ('' is
  // unrated). A linked bundle inherits its rating and never sends this.
  content_rating: string;
}

export interface EditableMediaCollection {
  title: string;
  description: string | null;
  content_rating: string | null;
}

// Simpler than Game's/App's: no launch-disc leaf traversal needed.
export function formFromCollection(c: EditableMediaCollection): SoftwareMediaForm {
  return {
    title: c.title,
    description: c.description ?? '',
    content_rating: c.content_rating ?? '',
  };
}
