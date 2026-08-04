// Wraps @radix-ui/react-radio-group. RadioGroup is the root, Radio is one
// option inside it, same visual language as Checkbox (border-border,
// bg-surface-2 at rest) but circular, with an accent-colored filled dot
// when selected instead of a checkmark.
//
// Usage:
//   <RadioGroup value={provider} onValueChange={setProvider}>
//     <Radio value="thegamesdb" label="TheGamesDB" />
//     <Radio value="igdb" label="IGDB" />
//   </RadioGroup>
//
// Props (RadioGroup):
//   value?: string
//   onValueChange?: (value: string) => void
//   disabled?: boolean
//   className?: string   default layout is a vertical stack, gap-2
//   children: ReactNode
//
// Props (Radio):
//   value: string        required, identifies this option within the group
//   id?: string
//   disabled?: boolean
//   label?: ReactNode
//   className?: string        merged onto the dot itself, not the wrapping label
//   wrapperClassName?: string merged onto the wrapping label (only applies
//                              when label is set). Radix's RadioGroup.Item
//                              carries data-state="checked"|"unchecked" on
//                              itself, not on the wrapper, so to highlight
//                              the whole row on selection use Tailwind's
//                              has-[] arbitrary variant targeting that
//                              descendant attribute, not data-[state=checked]
//                              directly (that only matches the dot itself):
//                                wrapperClassName="rounded-md border border-border
//                                  px-3 py-2 has-[[data-state=checked]]:border-accent
//                                  has-[[data-state=checked]]:bg-surface-2"

import * as RadixRadioGroup from '@radix-ui/react-radio-group';
import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface RadioGroupProps {
  value?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}

export function RadioGroup({
  value,
  onValueChange,
  disabled,
  className,
  children,
}: RadioGroupProps) {
  return (
    <RadixRadioGroup.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      className={cn('flex flex-col gap-2', className)}
    >
      {children}
    </RadixRadioGroup.Root>
  );
}

interface RadioProps {
  value: string;
  id?: string;
  disabled?: boolean;
  label?: ReactNode;
  className?: string;
  wrapperClassName?: string;
}

export function Radio({ value, id, disabled, label, className, wrapperClassName }: RadioProps) {
  const dot = (
    <RadixRadioGroup.Item
      value={value}
      id={id}
      disabled={disabled}
      className={cn(
        'flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 focus:outline-none focus:ring-2 focus:ring-accent data-[state=checked]:border-accent disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
    >
      <RadixRadioGroup.Indicator className="h-2 w-2 rounded-full bg-accent" />
    </RadixRadioGroup.Item>
  );

  if (!label) return dot;

  return (
    <label className={cn('flex items-center gap-3', wrapperClassName)}>
      {dot}
      <span className="text-sm text-fg-1">{label}</span>
    </label>
  );
}
