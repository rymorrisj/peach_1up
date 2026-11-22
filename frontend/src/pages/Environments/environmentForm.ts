import {
  PC_PLATFORMS,
  PLATFORM_BACKENDS,
  type HardwareProfile,
  type Platform,
} from '@/generated/constants';

// A PC platform (kind "pc" in config/platforms.yaml). Membership is enforced
// at runtime by isPcPlatform and the backend.
export type PcPlatform = Platform;

export const PLATFORM_TO_EMULATOR: Record<string, string> = Object.fromEntries(
  PC_PLATFORMS.map((p) => [p, PLATFORM_BACKENDS[p]]),
);

// PC platforms whose Environments run on 86Box (installation media, VHD).
export const BOX86_PLATFORMS: ReadonlySet<string> = new Set(
  PC_PLATFORMS.filter((p) => PLATFORM_BACKENDS[p] === '86box'),
);

export interface EnvironmentForm {
  name: string;
  platform: PcPlatform | null;
  base_image_path: string;
  working_image_path: string;
  hardware_profile: HardwareProfile;
  machine_override: string;
  notes: string;
  launch_commands: string[];
}

export const EMPTY_ENV_FORM: EnvironmentForm = {
  name: '',
  platform: null,
  base_image_path: '',
  working_image_path: '',
  hardware_profile: 'standard',
  machine_override: '',
  notes: '',
  launch_commands: [],
};

// Whether a platform is PC (an Environment is chosen) rather than console
// (fixed platform-to-emulator mapping, no Environment).
export function isPcPlatform(platform: string): boolean {
  return PC_PLATFORMS.includes(platform);
}
