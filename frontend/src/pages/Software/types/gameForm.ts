import type { BaseSoftwareForm } from './softwareForm';

export interface SoftwareGameForm extends BaseSoftwareForm {
  sort_title: string;
  publisher: string;
  year: string;
  category: string;
  content_rating: string;
  era: string;
  environment_item_id: string;
  profile_item_id: string;
  executable_path: string;
}

interface EditableItem {
  id: number;
  cover_art_path: string | null;
  executable_path: string | null;
}

export interface EditableCollection {
  title: string;
  sort_title: string | null;
  description: string | null;
  publisher: string | null;
  year: number | null;
  category: string | null;
  content_rating: string | null;
  era: string;
  environment_item_id: number | null;
  profile_item_id: number | null;
  launch_disk_id: number | null;
  items: EditableItem[];
}

// Games-specific derivation, including the launch-disc lookup for
// cover_art_path/executable_path. Media/App items have no such traversal
// (no launch-disc indirection), so this stays colocated with SoftwareGameForm
// rather than folded into the generalized useEditForm hook.
export function formFromCollection(c: EditableCollection): SoftwareGameForm {
  const launchDisc = c.items.find((i) => i.id === c.launch_disk_id) ?? c.items[0];
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
    environment_item_id: c.environment_item_id?.toString() ?? '',
    profile_item_id: c.profile_item_id?.toString() ?? '',
    executable_path: launchDisc?.executable_path ?? '',
  };
}
