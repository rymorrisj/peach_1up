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

export interface CatalogEntry {
  slug: string
  name: string
  version: string
  description: string
  license: string
  required: boolean
  is_installed: boolean
  install_path: string | null
  is_placeholder: boolean
  install_note?: string
}

export interface EmulatorInstallStatus {
  slug: string
  status: 'idle' | 'downloading' | 'complete' | 'error'
  error: string | null
  install_path: string | null
}
