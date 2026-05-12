// Re-exports generated types once `npm run generate:api` has been run
// export * from '@/api/generated'

export interface User {
  id: number
  name: string
  is_owner: boolean
  pin_required: boolean
  can_launch_media: boolean
  can_edit_platforms: boolean
  can_edit_library: boolean
  can_manage_profiles: boolean
  can_edit_settings: boolean
  is_admin: boolean
  max_content_rating: string | null
  block_unrated_media: boolean
  is_locked: boolean
  failed_pin_attempts: number
  created_at: string | null
  updated_at: string | null
}

export interface LibraryItem {
  id: number
  slug: string | null
  title: string
  sort_title: string | null
  era: string
  media_path: string
  profile_id: number | null
  platform_id: number | null
  category: string | null
  media_type: string | null
  cover_art_path: string | null
  description: string | null
  publisher: string | null
  year: number | null
  content_rating: string | null
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
  config_path: string | null
  is_bundled: boolean
  is_accuracy_mode: boolean
  enable_networking: boolean
  extra_args: string | null
  notes: string | null
  user_id: number | null
  created_at: string
  updated_at: string
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
  sandboxed: boolean
  sandbox_memory_limit_mb: number | null
  sandbox_cpu_limit_percent: number | null
}
