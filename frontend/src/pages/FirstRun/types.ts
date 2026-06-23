export interface EmulatorStatus {
  slug: string
  name: string
  required: boolean
  available: boolean
  path: string | null
}

export interface LibraryPaths {
  library_path: string | null
  media_path: string | null
  os_path: string | null
  profiles_path: string | null
  roms_path: string | null
}

export interface FirstRunStatus {
  first_run_complete: boolean
  owner_exists: boolean
  emulators: EmulatorStatus[]
  paths: LibraryPaths
}

export interface OwnerStatus {
  owner_broken: boolean
}

export interface EmulatorStatusData {
  slug: string
  install_type: 'zip' | 'installer' | 'rom_pack'
  binary_detected: boolean
  binary_path: string | null
  installer_present: boolean
  status: 'idle' | 'complete' | 'error' | 'installer_launched' | 'cloning'
  error: string | null
  install_path: string | null
}
