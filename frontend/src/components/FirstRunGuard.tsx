import { Navigate, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import OwnerBroken from '@/pages/OwnerBroken';
import { apiFetch } from '@/api/client';
import type { FirstRunStatus, OwnerStatus } from '@/pages/FirstRun/types';

export function FirstRunGuard() {
  const { data, isLoading } = useQuery({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch<FirstRunStatus>('/api/v1/settings/first-run-status'),
  });

  const firstRunComplete = data?.first_run_complete ?? false;

  // Only relevant once first-run setup is done, true first-run (no owner
  // yet) is FirstRun's job, not this fallback's.
  const ownerStatus = useQuery({
    queryKey: ['owner-status'],
    queryFn: () => apiFetch<OwnerStatus>('/api/v1/settings/owner-status'),
    enabled: firstRunComplete,
  });

  if (isLoading || (firstRunComplete && ownerStatus.isLoading)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-0">
        <LoadingSpinner label="Checking setup status…" />
      </main>
    );
  }

  if (data && !data.first_run_complete) {
    return <Navigate to="/first-run" replace />;
  }

  if (ownerStatus.data?.owner_broken) {
    return <OwnerBroken />;
  }

  return <Outlet />;
}
