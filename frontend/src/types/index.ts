// Re-exports generated types once `npm run generate:api` has been run
// export * from '@/api/generated'

export interface LibraryItem {
  id: number
  title: string
  era: string
  media_path: string
  profile_id: number | null
  platform_id: number | null
  category: string | null
  media_type: string | null
  last_launched_at: string | null
  launch_count: number
  created_at: string
  updated_at: string
}

export interface Platform {
  id: number
  name: string
  slug: string | null
  era: string
  emulator_slug: string
  profile_id: number | null
  base_image_path: string | null
  working_image_path: string | null
  config_path: string | null
  status: string
  notes: string | null
  last_health_check: string | null
  is_system: boolean
  download_url: string | null
  supported_eras: string | null
  default_flags: string | null
  created_at: string
  updated_at: string
}

export interface LaunchProfile {
  id: number
  name: string
  slug: string
  emulator_slug: string
  era: string
  is_bundled: boolean
  is_accuracy_mode: boolean
  extra_args: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface UserProfile {
  id: number
  name: string
  avatar_path: string | null
  is_owner: boolean
  platform_slug: string | null
  era: string | null
  custom_flags: string | null
  rom_pack_path: string | null
  custom_script: string | null
  notes: string | null
  created_at: string
  last_active_at: string | null
}

export interface LaunchHistory {
  id: number
  library_item_id: number
  profile_id: number | null
  emulator_slug: string
  started_at: string
  ended_at: string | null
  exit_code: number | null
  error_message: string | null
  network_blocked: boolean
  job_isolated: boolean
}
