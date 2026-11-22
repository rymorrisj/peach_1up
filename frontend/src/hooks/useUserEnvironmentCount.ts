import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/api/client';
import type { components } from '@shared/types';

type Environment = components['schemas']['EnvironmentItemRead'];

// Number of Environments the Environments page lists (system rows excluded),
// from the same query. undefined until loaded.
export function useUserEnvironmentCount(enabled: boolean): number | undefined {
  const { data } = useQuery<Environment[]>({
    queryKey: ['environments'],
    queryFn: () => apiFetch<Environment[]>('/api/v1/environment-items'),
    enabled,
  });
  return data?.filter((e) => !e.is_system).length;
}
