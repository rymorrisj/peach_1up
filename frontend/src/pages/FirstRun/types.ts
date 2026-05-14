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
  emulators: EmulatorStatus[]
  paths: LibraryPaths
}

export interface CatalogEntry {
  slug: string
  name: string
  version: string
  description: string
  license: string
  copyright?: string
  source_url?: string
  install_type: 'zip' | 'installer' | 'rom_pack'
  install_scope: 'portable' | 'system'
  required: boolean
  is_installed: boolean
  install_path: string | null
  installer_present: boolean
  git_available: boolean | null
  expert_mode_set?: boolean
  supported_formats?: string[]
  install_note?: string
  guidance_text?: string
  guidance_url?: string
}

export interface EmulatorInstallStatus {
  slug: string
  status: 'idle' | 'complete' | 'error' | 'installer_launched' | 'cloning'
  error: string | null
  install_path: string | null
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

export interface BiosRequirement {
  slug: string
  name: string
  platform: string
  bios_path: string
  guidance_text: string
  guidance_url: string
  is_present: boolean
}
