import type { components } from '@shared/types'
import type { EmulatorCatalogSlug } from '@/generated/constants'

export type LaunchProfile = components['schemas']['ProfileRead']
export type DriveRecord = components['schemas']['DriveRead'] & { slug: string; era: string }
export type EmulatorEntry = components['schemas']['CatalogEntryResponse']

export type DriveMode = 'none' | 'existing' | 'create'

export interface ProfileForm {
  name: string
  slug: string
  emulator_slug: EmulatorCatalogSlug | ''
  era: string
  extra_args: string
  enable_networking: boolean
  enable_dgvoodoo2: boolean
  notes: string
  launch_commands: string[]
  container_enabled: boolean | null
  drive_mode: DriveMode
  drive_slug: string
  new_drive_name: string
  new_drive_size_mb: number
}

export type ProfileModalState =
  | null
  | { mode: 'create' }
  | { mode: 'edit'; profile: LaunchProfile }
