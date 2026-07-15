import type { BaseSoftwareForm } from './softwareForm'

// is_pc stays boolean, not string, unlike era/environment_item_id below,
// since it's toggle-driven rather than a text/select control value and
// mirrors AppItemBundleData.is_pc directly. Not independently settable by
// the user though: the backend derives is_pc from era on every write and
// rejects a conflicting value (AppItemBundle._validate_is_pc), so the form
// component keeps this in sync with era rather than exposing its own
// checkbox for it.
export interface SoftwareAppForm extends BaseSoftwareForm {
  is_pc: boolean
  era: string
  environment_item_id: string
}

export interface EditableAppCollection {
  title: string
  description: string | null
  era: string
  is_pc: boolean
  environment_item_id: number | null
  display_disk_id: number | null
  launch_disk_id: number | null
  items: { id: number; cover_art_path: string | null }[]
}

// App is always a collection-of-one (see create_app_item_bundle), but cover
// art still lives on the leaf item, not the bundle (mirrors Game's leaf
// indirection, same display/launch disk id precedence as resolveLeafCoverArt
// in ../types.ts), confirmed against backend/models/app.py rather than
// assumed, since Media's cover_art_path lives directly on the bundle instead.
export function formFromCollection(c: EditableAppCollection): SoftwareAppForm {
  const effectiveLeafId = c.display_disk_id ?? c.launch_disk_id
  const leaf = c.items.find((i) => i.id === effectiveLeafId) ?? c.items[0]
  return {
    title: c.title,
    description: c.description ?? '',
    cover_art_path: leaf?.cover_art_path ?? '',
    is_pc: c.is_pc,
    era: c.era && c.era !== 'unknown' ? c.era : '',
    environment_item_id: c.environment_item_id?.toString() ?? '',
  }
}
