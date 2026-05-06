import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import AppShell from '@/components/layout/AppShell'
import Library from '@/pages/Library'
import Detail from '@/pages/Detail'
import Platforms from '@/pages/Platforms'
import Profiles from '@/pages/Profiles'
import Settings from '@/pages/Settings'
import FirstRun from '@/pages/FirstRun'
import NotFound from '@/pages/NotFound'
import '@/styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/library" replace />} />
            <Route element={<AppShell />}>
              <Route path="/library" element={<Library />} />
              <Route path="/library/:id" element={<Detail />} />
              <Route path="/platforms" element={<Platforms />} />
              <Route path="/profiles" element={<Profiles />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
            <Route path="/first-run" element={<FirstRun />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AppProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
