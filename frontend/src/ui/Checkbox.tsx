// Wraps @radix-ui/react-checkbox. When a label is passed the whole thing
// renders as <label className="flex items-center gap-3">box + text</label>,
// matching the hand-rolled pattern in AdvancedTab.tsx's checkbox rows
// (input + <span className="text-sm ...">) so migrating those call sites
// later is a near drop-in, swap the <input type="checkbox"> block for
// <Checkbox checked={...} onCheckedChange={...} label={...} />.
//
// Usage:
//   <Checkbox
//     id="delete-original"
//     checked={enabled}
//     onCheckedChange={handleToggle}
//     disabled={saving}
//     label='Delete the original file/folder after importing via "Browse Server Files…"'
//   />
//
//   <Checkbox checked={selected} onCheckedChange={setSelected} />   // no label, box only
//
// Props:
//   checked?: boolean
//   onCheckedChange?: (checked: boolean) => void
//   disabled?: boolean
//   id?: string
//   label?: ReactNode
//   size?: 'sm' | 'md'         default 'md' (h-4 w-4, text-sm label). 'sm' is
//                               h-3.5 w-3.5 with a text-xs label, for dense
//                               list-row usage like a per-entry checkbox.
//   className?: string         merged onto the box itself, not the label
//   labelClassName?: string    merged onto the label span, overrides the
//                               default text-fg-1 (e.g. a warning-toned label)

import * as RadixCheckbox from '@radix-ui/react-checkbox';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

type CheckboxSize = 'sm' | 'md';

interface CheckboxProps {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  label?: ReactNode;
  size?: CheckboxSize;
  className?: string;
  labelClassName?: string;
}

const BOX_SIZE: Record<CheckboxSize, string> = {
  sm: 'h-3.5 w-3.5',
  md: 'h-4 w-4',
};

const LABEL_SIZE: Record<CheckboxSize, string> = {
  sm: 'text-xs',
  md: 'text-sm',
};

const CHECK_SIZE: Record<CheckboxSize, number> = {
  sm: 10,
  md: 12,
};

export function Checkbox({
  checked,
  onCheckedChange,
  disabled,
  id,
  label,
  size = 'md',
  className,
  labelClassName,
}: CheckboxProps) {
  const box = (
    <RadixCheckbox.Root
      id={id}
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      className={cn(
        'flex shrink-0 items-center justify-center rounded border border-border bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:cursor-not-allowed disabled:opacity-50',
        BOX_SIZE[size],
        className,
      )}
    >
      <RadixCheckbox.Indicator>
        <Check size={CHECK_SIZE[size]} strokeWidth={3} className="text-accent-fg" />
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  );

  if (!label) return box;

  return (
    <label className="flex items-center gap-3">
      {box}
      <span className={cn(LABEL_SIZE[size], 'text-fg-1', labelClassName)}>{label}</span>
    </label>
  );
}
