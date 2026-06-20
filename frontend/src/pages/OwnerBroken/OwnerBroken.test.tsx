import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Navigate, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import OwnerBroken from '@/pages/OwnerBroken'
import type { FirstRunStatus, OwnerStatus } from '@/pages/FirstRun/types'

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
}))

// Mirrors the FirstRunGuard component in src/main.tsx — kept in sync manually
// since main.tsx bootstraps ReactDOM.createRoot and isn't itself importable.
function FirstRunGuard() {
  const { data, isLoading } = useQuery({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch<FirstRunStatus>('/api/v1/settings/first-run-status'),
  })

  const firstRunComplete = data?.first_run_complete ?? false

  const ownerStatus = useQuery({
    queryKey: ['owner-status'],
    queryFn: () => apiFetch<OwnerStatus>('/api/v1/settings/owner-status'),
    enabled: firstRunComplete,
  })

  if (isLoading || (firstRunComplete && ownerStatus.isLoading)) {
    return <div data-testid="loading">loading</div>
  }

  if (data && !data.first_run_complete) {
    return <Navigate to="/first-run" replace />
  }

  if (ownerStatus.data?.owner_broken) {
    return <OwnerBroken />
  }

  return <Outlet />
}

function renderGuard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/library']}>
        <Routes>
          <Route path="/first-run" element={<div data-testid="first-run">first-run</div>} />
          <Route element={<FirstRunGuard />}>
            <Route path="/library" element={<div data-testid="app">normal app</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('FirstRunGuard owner-broken fallback', () => {
  afterEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('renders the OwnerBroken fallback when owner_broken is true', async () => {
    vi.mocked(apiFetch).mockImplementation((path: string) => {
      if (path.includes('first-run-status')) {
        return Promise.resolve<FirstRunStatus>({
          first_run_complete: true,
          owner_exists: true,
          emulators: [],
          paths: { library_path: null, media_path: null, os_path: null, profiles_path: null, roms_path: null },
        })
      }
      if (path.includes('owner-status')) {
        return Promise.resolve<OwnerStatus>({ owner_broken: true })
      }
      return Promise.reject(new Error(`unexpected path: ${path}`))
    })

    renderGuard()

    await waitFor(() => expect(screen.getByText(/owner account unavailable/i)).toBeInTheDocument())
    expect(screen.getByText('python scripts/setup_admin_user.py')).toBeInTheDocument()
    expect(screen.queryByTestId('app')).not.toBeInTheDocument()
  })

  it('renders the normal app when owner is present and not locked', async () => {
    vi.mocked(apiFetch).mockImplementation((path: string) => {
      if (path.includes('first-run-status')) {
        return Promise.resolve<FirstRunStatus>({
          first_run_complete: true,
          owner_exists: true,
          emulators: [],
          paths: { library_path: null, media_path: null, os_path: null, profiles_path: null, roms_path: null },
        })
      }
      if (path.includes('owner-status')) {
        return Promise.resolve<OwnerStatus>({ owner_broken: false })
      }
      return Promise.reject(new Error(`unexpected path: ${path}`))
    })

    renderGuard()

    await waitFor(() => expect(screen.getByTestId('app')).toBeInTheDocument())
  })
})
