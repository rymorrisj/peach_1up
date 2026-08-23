import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ToastEventBridge } from '@/components/ToastEventBridge';
import { RequireAuth } from '@/components/RequireAuth';
import { FirstRunGuard } from '@/components/FirstRunGuard';
import AppShell from '@/components/layout/AppShell';
import Software from '@/pages/Software';
import { softwareTabRoutes } from '@/pages/Software/tabs';
import CollectionDetail from '@/pages/Software/CollectionDetail';
import MediaDetail from '@/pages/Software/MediaDetail';
import AppDetail from '@/pages/Software/AppDetail';
import Settings from '@/pages/Settings';
import Users from '@/pages/Users';
import Emulators from '@/pages/Emulators';
import { emulatorsTabRoutes } from '@/pages/Emulators/tabs';
import EmulatorDetail from '@/pages/Emulators/EmulatorDetail';
import Environments from '@/pages/Environments';
import EnvironmentDetail from '@/pages/Environments/EnvironmentDetail';
import Tags from '@/pages/Tags';
import System from '@/pages/System';
import { systemTabRoutes } from '@/pages/System/tabs';
import FirstRun from '@/pages/FirstRun';
import NotFound from '@/pages/NotFound';
import '@/styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

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
