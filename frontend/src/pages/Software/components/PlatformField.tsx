import { FormField, Select } from '@/ui';
import type { components } from '@shared/types';

// Extends the generated EnvironmentItemRead with launch_blocked_reason, not
// yet present in shared/types.ts (typed Optional[str] on the backend model,
// same as GameItemBundleRead/AppItemBundleRead's own launch_blocked_reason
// field, see backend/models/environment.py) until the OpenAPI export is
// regenerated. Extended locally rather than hand-edited into the generated
// file.
type Platform = components['schemas']['EnvironmentItemRead'] & {
  launch_blocked_reason?: string | null;
};

interface PlatformFieldProps {
  /** Whether this item can launch via an Environment at all (Games: era is
   *  PC, Apps: is_pc). Everything else about the field derives from this. */
  isPcLaunchable: boolean;
  value: string;
  onChange: (value: string) => void;
  platforms: Platform[];
  /** Shown as the field's hint only while disabled, explaining why there is
   *  no Environment picker for this item. */
  disabledNote: string;
}

// Maps era_defaults.LaunchBlockedReason's string values (backend/service/
// utils/era_defaults.py) to the option label shown next to a disabled
// candidate. The reason itself is computed server-side, by
// GET /api/v1/environment-items?era=<item era>, looping evaluate_launch_
// readiness() per row, this component no longer re-implements era-match,
// presence, or installed checks of its own; an unrecognized reason string
// falls back to showing the raw code rather than hiding it.
const REASON_LABELS: Record<string, string> = {
  environment_era_mismatch: 'different era',
  environment_not_present: 'not present',
  environment_not_provisioned: 'not yet provisioned',
  environment_not_installed: 'OS not installed yet',
};

function unselectableReason(p: Platform): string | null {
  const reason = p.launch_blocked_reason;
  if (!reason) return null;
  return REASON_LABELS[reason] ?? reason;
}

// Shared by EditForm.tsx (Games, gated on era) and AppEditForm.tsx (Apps,
// gated on is_pc) so the enabled/disabled-with-note behavior lives in one
// place instead of being reimplemented per domain. Console items have no
// per-item Environment (the era-to-emulator mapping is fixed), so the field
// stays visible but disabled rather than being hidden, per the "Platform"
// label's existing meaning, only what populates and gates it changes here.
//
// Per-option gating mirrors the same disabled+note pattern used for the
// whole field: an Environment the server reports as blocked shows as a
// disabled option with the reason appended, rather than being silently
// omitted or silently selectable, same "explain why, don't hide" philosophy
// as the field-level disabledNote.
export function PlatformField({
  isPcLaunchable,
  value,
  onChange,
  platforms,
  disabledNote,
}: PlatformFieldProps) {
  return (
    <FormField
      label="Platform"
      htmlFor="detail-platform"
      hint={!isPcLaunchable ? disabledNote : undefined}
    >
      <Select
        id="detail-platform"
        value={value || 'none'}
        disabled={!isPcLaunchable}
        onValueChange={(v) => onChange(v === 'none' ? '' : v)}
        options={[
          { value: 'none', label: 'No platform selected' },
          ...(isPcLaunchable
            ? platforms.map((p) => {
                const reason = unselectableReason(p);
                return {
                  value: String(p.id),
                  label: reason ? `${p.name}, ${reason}` : p.name,
                  disabled: reason != null,
                };
              })
            : []),
        ]}
      />
    </FormField>
  );
}
