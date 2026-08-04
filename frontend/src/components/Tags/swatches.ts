import { TAG_COLOR_HEX, type TagColor } from '@/generated/constants';

export const TAG_SWATCHES: { id: TagColor; hex: string }[] = Object.entries(TAG_COLOR_HEX).map(
  ([id, hex]) => ({ id: id as TagColor, hex }),
);

export function swatchHex(colorId: string): string {
  return TAG_COLOR_HEX[colorId] ?? '#7a8499';
}
