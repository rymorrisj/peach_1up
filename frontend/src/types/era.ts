export const ERA_LABEL: Record<string, string> = {
  dos: 'DOS', win95: 'WIN95', win98: 'WIN98', winxp: 'WINXP',
  ps1: 'PS1', ps2: 'PS2', xbox: 'XBOX', dreamcast: 'DC',
  nes: 'NES', n64: 'N64', snes: 'SNES',
}

export const ERA_COLOR: Record<string, string> = {
  DOS: 'var(--era-dos)',
  WIN95: 'var(--era-win95)',
  WIN98: 'var(--era-win98)',
  WINXP: 'var(--era-winxp)',
  PS1: '#a9a0d6',
  PS2: '#6090d0',
  XBOX: '#6db36d',
  DC: '#d0a060',
  NES: '#d06060',
  N64: '#60a0d0',
  SNES: '#d4a0c0',
}

export const ERA_PLACEHOLDER: Record<string, { bg: string; color: string }> = {
  dos:        { bg: 'linear-gradient(155deg, #2b2316 0%, #16110a 100%)', color: 'var(--era-dos)' },
  win95:      { bg: 'linear-gradient(155deg, #20281a 0%, #11160c 100%)', color: 'var(--era-win95)' },
  win98:      { bg: 'linear-gradient(155deg, #17202b 0%, #0c1118 100%)', color: 'var(--era-win98)' },
  winxp:      { bg: 'linear-gradient(155deg, #182617 0%, #0e150d 100%)', color: 'var(--era-winxp)' },
  ps1:        { bg: 'linear-gradient(155deg, #1e1a2b 0%, #110f18 100%)', color: '#a9a0d6' },
  ps2:        { bg: 'linear-gradient(155deg, #162030 0%, #0c1118 100%)', color: '#6090d0' },
  xbox:       { bg: 'linear-gradient(155deg, #182618 0%, #0e150e 100%)', color: '#6db36d' },
  dreamcast:  { bg: 'linear-gradient(155deg, #2b2416 0%, #181208 100%)', color: '#d0a060' },
  nes:        { bg: 'linear-gradient(155deg, #2b1616 0%, #180e0e 100%)', color: '#d06060' },
  n64:        { bg: 'linear-gradient(155deg, #162028 0%, #0c1016 100%)', color: '#60a0d0' },
  snes:       { bg: 'linear-gradient(155deg, #281624 0%, #160e14 100%)', color: '#d4a0c0' },
}

export const ERA_PLACEHOLDER_DEFAULT = { bg: 'linear-gradient(155deg, #1c2230 0%, #11141c 100%)', color: '#6aa9d6' }

export const EMULATOR_ERA_MAP: Record<string, string[]> = {
  'dosbox-x':   ['DOS'],
  '86box':      ['WIN95', 'WIN98', 'WINXP'],
  duckstation:  ['PS1'],
  pcsx2:        ['PS2'],
  xemu:         ['XBOX'],
  flycast:      ['DC'],
  mesen:        ['NES', 'SNES'],
  project64:    ['N64'],
}
