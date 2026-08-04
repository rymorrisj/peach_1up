// Wraps @radix-ui/react-select. Flat options array API, same shape a native
// <select> plus <option> list would take, so it is a near drop-in for the
// existing SELECT_CLASS + <option>.map() pattern used across the app.
// Also accepts grouped entries ({ groupLabel, options }) mixed into the same
// array, for call sites that need <optgroup>-style sections (e.g. Launch
// Profile's "Matching era" / "Other eras"). Flat and grouped entries can be
// mixed in one options array, group detection is structural (does the entry
// have a groupLabel), not a separate prop, so existing flat-only call sites
// keep working unchanged.
//
// Usage:
//   <Select
//     value={form.content_rating}
//     onValueChange={(v) => setField('content_rating', v)}
//     options={RATING_OPTIONS}
//     placeholder="Select a rating"
//   />
//
//   <Select value={era} onValueChange={setEra} options={eraOptions} hasError={!era} disabled={saving} />
//
//   <Select
//     value={profileId}
//     onValueChange={setProfileId}
//     options={[
//       { value: 'none', label: '— No profile —' },
//       { groupLabel: 'Matching era', options: eraProfileOptions },
//       { groupLabel: 'Other eras', options: otherProfileOptions },
//     ]}
//   />
//
// Props:
//   value?: string
//   onValueChange?: (value: string) => void
//   options: (SelectOption | SelectOptionGroup)[]
//   placeholder?: string
//   disabled?: boolean
//   hasError?: boolean
//   id?: string          forwarded to the trigger, pair with FormField's htmlFor
//   className?: string   merged onto the trigger

import * as RadixSelect from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectOptionGroup {
  groupLabel: string;
  options: SelectOption[];
}

type SelectEntry = SelectOption | SelectOptionGroup;

function isGroup(entry: SelectEntry): entry is SelectOptionGroup {
  return 'groupLabel' in entry;
}

interface SelectProps {
  value?: string;
  onValueChange?: (value: string) => void;
  options: SelectEntry[];
  placeholder?: string;
  disabled?: boolean;
  hasError?: boolean;
  id?: string;
  className?: string;
}

function SelectItemRow({ option }: { option: SelectOption }) {
  return (
    <RadixSelect.Item
      value={option.value}
      disabled={option.disabled}
      className="relative flex cursor-pointer select-none items-center rounded px-6 py-1.5 text-sm text-fg-1 outline-none data-[highlighted]:bg-surface-2 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
    >
      <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
      <RadixSelect.ItemIndicator className="absolute left-1.5 inline-flex items-center">
        <Check size={14} className="text-accent" />
      </RadixSelect.ItemIndicator>
    </RadixSelect.Item>
  );
}

export function Select({
  value,
  onValueChange,
  options,
  placeholder,
  disabled,
  hasError,
  id,
  className,
}: SelectProps) {
  return (
    <RadixSelect.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <RadixSelect.Trigger
        id={id}
        className={cn(
          'flex w-full items-center justify-between gap-2 rounded-md border bg-surface-2 px-3 py-2 text-sm text-fg-1 focus:outline-none focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50',
          hasError ? 'border-error focus:ring-error' : 'border-border',
          className,
        )}
      >
        <RadixSelect.Value placeholder={placeholder} className="data-[placeholder]:text-fg-3" />
        <RadixSelect.Icon>
          <ChevronDown size={14} className="shrink-0 text-fg-3" />
        </RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        {/* position="popper" is required for the trigger-width CSS var below
            to be exposed. Without it Radix falls back to item-aligned
            positioning and the dropdown width no longer tracks the trigger. */}
        <RadixSelect.Content
          position="popper"
          sideOffset={4}
          className="z-50 w-[var(--radix-select-trigger-width)] max-h-[var(--radix-select-content-available-height)] overflow-hidden rounded-md border border-border bg-surface-1 shadow-lg"
        >
          <RadixSelect.Viewport className="p-1">
            {options.map((entry, i) =>
              isGroup(entry) ? (
                <RadixSelect.Group key={`group-${entry.groupLabel}-${i}`}>
                  <RadixSelect.Label className="px-6 py-1.5 text-xs font-semibold uppercase tracking-wider text-fg-3">
                    {entry.groupLabel}
                  </RadixSelect.Label>
                  {entry.options.map((opt) => (
                    <SelectItemRow key={opt.value} option={opt} />
                  ))}
                </RadixSelect.Group>
              ) : (
                <SelectItemRow key={entry.value} option={entry} />
              ),
            )}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
