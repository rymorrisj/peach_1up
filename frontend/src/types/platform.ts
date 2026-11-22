import {
  PLATFORM_BACKENDS,
  PLATFORM_KINDS,
  PLATFORM_LABELS,
  type ItemType,
} from '../generated/constants';
import type { SelectOption, SelectOptionGroup } from '../ui/Select';

export const PLATFORM_SHORT_LABEL: Record<string, string> = {
  dos: 'DOS',
  win95: 'WIN95',
  win98: 'WIN98',
  winxp: 'WINXP',
  ps1: 'PS1',
  ps2: 'PS2',
  xbox: 'XBOX',
  dreamcast: 'DC',
  nes: 'NES',
  n64: 'N64',
  snes: 'SNES',
};

export const PLATFORM_COLOR: Record<string, string> = {
  DOS: 'rgb(var(--platform-dos))',
  WIN95: 'rgb(var(--platform-win95))',
  WIN98: 'rgb(var(--platform-win98))',
  WINXP: 'rgb(var(--platform-winxp))',
  PS1: '#a9a0d6',
  PS2: '#6090d0',
  XBOX: '#6db36d',
  DC: '#d0a060',
  NES: '#d06060',
  N64: '#60a0d0',
  SNES: '#d4a0c0',
};

export const PLATFORM_PLACEHOLDER: Record<string, { bg: string; color: string }> = {
  dos: {
    bg: 'linear-gradient(155deg, #2b2316 0%, #16110a 100%)',
    color: 'rgb(var(--platform-dos))',
  },
  win95: {
    bg: 'linear-gradient(155deg, #20281a 0%, #11160c 100%)',
    color: 'rgb(var(--platform-win95))',
  },
  win98: {
    bg: 'linear-gradient(155deg, #17202b 0%, #0c1118 100%)',
    color: 'rgb(var(--platform-win98))',
  },
  winxp: {
    bg: 'linear-gradient(155deg, #182617 0%, #0e150d 100%)',
    color: 'rgb(var(--platform-winxp))',
  },
  ps1: { bg: 'linear-gradient(155deg, #1e1a2b 0%, #110f18 100%)', color: '#a9a0d6' },
  ps2: { bg: 'linear-gradient(155deg, #162030 0%, #0c1118 100%)', color: '#6090d0' },
  xbox: { bg: 'linear-gradient(155deg, #182618 0%, #0e150e 100%)', color: '#6db36d' },
  dreamcast: { bg: 'linear-gradient(155deg, #2b2416 0%, #181208 100%)', color: '#d0a060' },
  nes: { bg: 'linear-gradient(155deg, #2b1616 0%, #180e0e 100%)', color: '#d06060' },
  n64: { bg: 'linear-gradient(155deg, #162028 0%, #0c1016 100%)', color: '#60a0d0' },
  snes: { bg: 'linear-gradient(155deg, #281624 0%, #160e14 100%)', color: '#d4a0c0' },
};

export const PLATFORM_PLACEHOLDER_DEFAULT = {
  bg: 'linear-gradient(155deg, #1c2230 0%, #11141c 100%)',
  color: '#6aa9d6',
};

// Derived from the generated platform->emulator map (config/platforms.yaml backend)
// by inverting to emulator->platforms, the shape existing consumers (Emulators pages) expect.
export const EMULATOR_PLATFORM_MAP: Record<string, string[]> = Object.entries(
  PLATFORM_BACKENDS,
).reduce(
  (acc, [platform, emulator]) => {
    const label = PLATFORM_SHORT_LABEL[platform] ?? platform.toUpperCase();
    (acc[emulator] ??= []).push(label);
    return acc;
  },
  {} as Record<string, string[]>,
);

export interface PlatformGroup {
  kind: ItemType;
  label: string;
  platforms: { value: string; label: string }[];
}

// Every known platform grouped PC then Console, from the generated
// PLATFORM_KINDS (config/platforms.yaml kind). "unknown" belongs to neither.
export const PLATFORM_GROUPS: PlatformGroup[] = (
  [
    { kind: 'pc', label: 'PC' },
    { kind: 'console', label: 'Console' },
  ] as const
).map(({ kind, label }) => ({
  kind,
  label,
  platforms: Object.entries(PLATFORM_KINDS)
    .filter(([, k]) => k === kind)
    .map(([value]) => ({ value, label: PLATFORM_LABELS[value] ?? value })),
}));

// Options for a Platform <Select>: a "none" entry, PC and Console groups, then Unknown.
export function platformSelectOptions(noneLabel: string): (SelectOption | SelectOptionGroup)[] {
  return [
    { value: 'none', label: noneLabel },
    ...PLATFORM_GROUPS.map((g) => ({ groupLabel: g.label, options: g.platforms })),
    { value: 'unknown', label: PLATFORM_LABELS.unknown ?? 'Unknown' },
  ];
}
