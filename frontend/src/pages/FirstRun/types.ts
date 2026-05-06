export interface EmulatorStatus {
  slug: string
  name: string
  required: boolean
  available: boolean
  path: string | null
}

export interface LibraryPaths {
  images_path: string | null
  profiles_path: string | null
  rom_path: string | null
}

export interface FirstRunStatus {
  first_run_complete: boolean
  owner_profile_exists: boolean
  emulators: EmulatorStatus[]
  paths: LibraryPaths
}
