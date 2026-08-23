import type { HardwareProfile } from '@/generated/constants';

export type PCEra = 'dos' | 'win95' | 'win98' | 'winxp';

export const ERA_TO_EMULATOR: Record<PCEra, string> = {
  dos: 'dosbox-x',
  win95: '86box',
  win98: '86box',
  winxp: '86box',
};

export interface EnvironmentForm {
  name: string;
  era: PCEra | null;
  base_image_path: string;
  working_image_path: string;
  hardware_profile: HardwareProfile;
  machine_override: string;
  notes: string;
  launch_commands: string[];
}

export const EMPTY_ENV_FORM: EnvironmentForm = {
  name: '',
  era: null,
  base_image_path: '',
  working_image_path: '',
  hardware_profile: 'standard',
  machine_override: '',
  notes: '',
  launch_commands: [],
};

// Whether an item's era makes it PC-launchable (Environment-driven) rather
// than console (fixed era-to-emulator mapping, no per-item Environment
// picker). Same membership check AppEditForm's handleEraChange already uses
// to keep is_pc in sync with era, pulled out so Games' Platform-field gating
// (era-based) can share it without duplicating the check.
export function isPcEra(era: string): boolean {
  return era in ERA_TO_EMULATOR;
}
