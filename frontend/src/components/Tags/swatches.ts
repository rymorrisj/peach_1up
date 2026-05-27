export const TAG_SWATCHES = [
  { id: 'slate',  hex: '#7a8499' },
  { id: 'coral',  hex: '#e07463' },
  { id: 'amber',  hex: '#d4954a' },
  { id: 'mint',   hex: '#59b87a' },
  { id: 'sky',    hex: '#5ba4cf' },
  { id: 'violet', hex: '#8b6dc4' },
  { id: 'rose',   hex: '#c46d8b' },
]

export function swatchHex(colorId: string): string {
  return TAG_SWATCHES.find((s) => s.id === colorId)?.hex ?? '#7a8499'
}
