import type { components } from '@shared/types'

export type LaunchProfile = components['schemas']['ProfileRead']
export type DriveRecord = components['schemas']['DriveRead']
export type EmulatorEntry = components['schemas']['CatalogEntryResponse']

export type DriveMode = 'none' | 'existing' | 'create'

export interface ProfileForm {
  name: string
  slug: string
  emulator_slug: string
  era: string
  extra_args: string
  enable_networking: boolean
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
