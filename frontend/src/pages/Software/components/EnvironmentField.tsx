import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiFetch } from '@/api/client';
import { FormField, Select } from '@/ui';
import { isPcPlatform } from '@/pages/Environments/environmentForm';
import { environmentBlockedReason } from '../types';
import type { components } from '@shared/types';

// launch_blocked_reason is set by GET /api/v1/environment-items?platform=...
type Environment = components['schemas']['EnvironmentItemRead'] & {
  launch_blocked_reason?: string | null;
};

interface EnvironmentFieldProps {
  /** The form's current platform, not the saved one. */
  platform: string;
  value: string;
  onChange: (value: string) => void;
}

// PC platforms only. Lists the same Environments as the Environments page
// (system rows excluded) with no compatibility filtering: the user chooses.
export function EnvironmentField({ platform, value, onChange }: EnvironmentFieldProps) {
  const isPc = isPcPlatform(platform);
  const { data: environments = [], isSuccess } = useQuery<Environment[]>({
    queryKey: ['environments', platform],
    queryFn: () =>
      apiFetch<Environment[]>(`/api/v1/environment-items?platform=${encodeURIComponent(platform)}`),
    enabled: isPc,
  });

  if (!isPc) return null;

  const userEnvironments = environments.filter((e) => !e.is_system);

  return (
    <FormField label="Environment" htmlFor="detail-environment">
      <Select
        id="detail-environment"
        value={value || 'none'}
        onValueChange={(v) => onChange(v === 'none' ? '' : v)}
        options={[
          { value: 'none', label: 'No environment selected' },
          ...userEnvironments.map((e) => {
            const reason = environmentBlockedReason(e.launch_blocked_reason);
            return {
              value: String(e.id),
              label: reason ? `${e.name}, ${reason}` : e.name,
              disabled: reason != null,
            };
          }),
        ]}
      />
      {isSuccess && userEnvironments.length === 0 && (
        <p className="mt-1 text-xs text-fg-3">
          No Environments yet.{' '}
          <Link to="/environments" className="text-blue-600 hover:underline dark:text-blue-400">
            Create one on the Environments page
          </Link>
          , then choose it here.
        </p>
      )}
    </FormField>
  );
}
