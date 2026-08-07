import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider, useToast } from '@/ui/ToastProvider';
import type { ToastVariant } from '@/ui/Toast';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import AppShell from '@/components/layout/AppShell';
import Software, { softwareTabRoutes } from '@/pages/Software';
import CollectionDetail from '@/pages/Software/CollectionDetail';
import MediaDetail from '@/pages/Software/MediaDetail';
import AppDetail from '@/pages/Software/AppDetail';
import Settings from '@/pages/Settings';
import Users from '@/pages/Users';
import Emulators, { emulatorsTabRoutes } from '@/pages/Emulators';
import EmulatorDetail from '@/pages/Emulators/EmulatorDetail';
import Environments from '@/pages/Environments';
import EnvironmentDetail from '@/pages/Environments/EnvironmentDetail';
import Tags from '@/pages/Tags';
import System, { systemTabRoutes } from '@/pages/System';
import FirstRun from '@/pages/FirstRun';
import NotFound from '@/pages/NotFound';
import OwnerBroken from '@/pages/OwnerBroken';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { apiFetch } from '@/api/client';
import { useAppContext } from '@/context/useAppContext';
import type { FirstRunStatus, OwnerStatus } from '@/pages/FirstRun/types';
import '@/styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

// Bridges window-level toast events (fired by non-React code such as the api
// client on api-error, or AppContext's background-job watcher) into the
// ToastProvider queue. Kept out of AppContext/api client so neither has to
// depend on the ToastProvider hook directly.
function ToastEventBridge() {
  const { showToast } = useToast();

  useEffect(() => {
    function handleApiError(e: Event) {
      const message = (e as CustomEvent<string>).detail ?? 'An unexpected error occurred.';
      showToast(message, 'error');
    }
    function handleAppToast(e: Event) {
      const { message, variant } = (e as CustomEvent<{ message: string; variant?: ToastVariant }>)
        .detail;
      showToast(message, variant ?? 'info');
    }
    window.addEventListener('api-error', handleApiError);
    window.addEventListener('app-toast', handleAppToast);
    return () => {
      window.removeEventListener('api-error', handleApiError);
      window.removeEventListener('app-toast', handleAppToast);
    };
  }, [showToast]);

  return null;
}

function RequireAuth() {
  const { state } = useAppContext();
  const location = useLocation();

  if (!state.authChecked) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-0">
        <LoadingSpinner label="Checking authentication…" />
      </main>
    );
  }

  if (!state.activeUser && !location.pathname.startsWith('/users')) {
    return <Navigate to="/users" replace />;
  }

  return <Outlet />;
}

function FirstRunGuard() {
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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ToastEventBridge />
          <AppProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/first-run" element={<FirstRun />} />
                <Route element={<FirstRunGuard />}>
                  <Route element={<RequireAuth />}>
                    <Route path="/" element={<Navigate to="/software" replace />} />
                    <Route element={<AppShell />}>
                      <Route path="/software" element={<Software />}>
                        {softwareTabRoutes}
                      </Route>
                      <Route path="/software/games/:slug" element={<CollectionDetail />} />
                      <Route path="/software/media/:id" element={<MediaDetail />} />
                      <Route path="/software/apps/:id" element={<AppDetail />} />
                      <Route path="/settings" element={<Settings />} />
                      <Route path="/users" element={<Users />} />
                      <Route path="/environments" element={<Environments />} />
                      <Route path="/environments/:id" element={<EnvironmentDetail />} />
                      <Route path="/emulators" element={<Emulators />}>
                        {emulatorsTabRoutes}
                      </Route>
                      <Route path="/emulators/:slug" element={<EmulatorDetail />} />
                      <Route path="/system" element={<System />}>
                        {systemTabRoutes}
                      </Route>
                      <Route
                        path="/platform-health"
                        element={<Navigate to="/system/health" replace />}
                      />
                      <Route path="/tags" element={<Tags />} />
                    </Route>
                  </Route>
                </Route>
                <Route path="*" element={<NotFound />} />
              </Routes>
            </BrowserRouter>
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
