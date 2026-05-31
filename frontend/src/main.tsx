import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import AppShell from '@/components/layout/AppShell'
import Library from '@/pages/Library'
import ItemDetail from '@/pages/Library/ItemDetail'
import Settings from '@/pages/Settings'
import GuidesIndex from '@/pages/Guides'
import CartridgeImaging from '@/pages/Guides/CartridgeImaging'
import BiosSourcing from '@/pages/Guides/BiosSourcing'
import Box86HardwareGuide from '@/pages/Guides/86BoxHardwareGuide'
import EraGuide from '@/pages/Guides/EraGuide'
import Emulators from '@/pages/Emulators'
import EmulatorDetail from '@/pages/Emulators/EmulatorDetail'
import Environments from '@/pages/Environments'
import EnvironmentDetail from '@/pages/Environments/EnvironmentDetail'
import DriveDetail from '@/pages/Drives/DriveDetail'
import Tags from '@/pages/Tags'
import Profiles from '@/pages/Settings/LaunchProfiles'
import ProfileDetail from '@/pages/Profiles/ProfileDetail'
import PlatformHealth from '@/pages/PlatformHealth'
import FirstRun from '@/pages/FirstRun'
import NotFound from '@/pages/NotFound'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import { apiFetch } from '@/api/client'
import type { FirstRunStatus } from '@/pages/FirstRun/types'
import '@/styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

function FirstRunGuard() {
  const { data, isLoading } = useQuery({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch<FirstRunStatus>('/api/v1/settings/first-run-status'),
  })

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950">
        <LoadingSpinner label="Checking setup status…" />
      </main>
    )
  }

  if (data && !data.first_run_complete) {
    return <Navigate to="/first-run" replace />
  }

  return <Outlet />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/first-run" element={<FirstRun />} />
            <Route element={<FirstRunGuard />}>
              <Route path="/" element={<Navigate to="/library" replace />} />
              <Route element={<AppShell />}>
                <Route path="/library" element={<Library />} />
                <Route path="/library/:slug" element={<ItemDetail />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/environments" element={<Environments />} />
                <Route path="/environments/:id" element={<EnvironmentDetail />} />
                <Route path="/drives/:slug" element={<DriveDetail />} />
                <Route path="/emulators" element={<Emulators />} />
                <Route path="/emulators/:slug" element={<EmulatorDetail />} />
                <Route path="/profiles" element={<Profiles />} />
                <Route path="/profiles/:slug" element={<ProfileDetail />} />
                <Route path="/platform-health" element={<PlatformHealth />} />
                <Route path="/tags" element={<Tags />} />
                <Route path="/guides" element={<GuidesIndex />} />
                <Route path="/guides/cartridge-imaging" element={<CartridgeImaging />} />
                <Route path="/guides/bios-sourcing" element={<BiosSourcing />} />
                <Route path="/guides/86box-hardware" element={<Box86HardwareGuide />} />
                <Route path="/guides/era-detection" element={<EraGuide />} />
              </Route>
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AppProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
