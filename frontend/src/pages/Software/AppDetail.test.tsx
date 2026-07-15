import { screen, waitFor, render } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import AppDetail from '@/pages/Software/AppDetail'
import { apiFetch } from '@/api/client'

// Basic smoke coverage only, not exhaustive behavior coverage (that's the
// existing CollectionDetail*.test.tsx depth, planned separately for a full
// audit before beta). This just catches a render-breaks-completely
// regression, same apiFetch-mocking approach as CollectionDetail's tests.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    detail: string
    constructor(status: number, detail: string) {
      super(detail)
      this.status = status
      this.detail = detail
      this.name = 'ApiError'
    }
  },
}))

const plainUser = {
  id: 1,
  name: 'Player',
  is_owner: false,
  is_admin: false,
  pin_required: false,
  can_launch_media: true,
  can_manage_environment: false,
  can_manage_game: false,
  can_manage_media: false,
  can_manage_app: false,
  can_manage_controllerMapping: false,
  can_manage_settings: false,
  can_manage_users: false,
  block_unrated_media: false,
  is_locked: false,
  failed_pin_attempts: 0,
}

function minimalApp(overrides?: Record<string, unknown>) {
  return {
    id: 1,
    slug: 'my-app',
    title: 'My App',
    description: null,
    tags: [],
    is_pc: true,
    category: null,
    publisher: null,
    developer: null,
    year: null,
    installed: false,
    environment_item_id: null,
    profile_item_id: null,
    launch_disk_id: 100,
    display_disk_id: 100,
    last_launched_at: null,
    launch_count: 0,
    items: [
      { id: 100, app_item_bundle_id: 1, file_path: '/apps/myapp.exe', executable_path: null, cover_art_path: null, cover_art_url: null },
    ],
    ...overrides,
  }
}

function mockApi(app: unknown) {
  vi.mocked(apiFetch).mockImplementation((url: unknown) => {
    if (typeof url !== 'string') return Promise.resolve([])
    if (url === '/api/v1/auth/me') return Promise.resolve(plainUser)
    if (url === '/api/v1/auth/refresh') return Promise.resolve({ user: plainUser })
    if (url === '/api/v1/app-item-bundle/1') return Promise.resolve(app)
    return Promise.resolve([])
  })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/software/apps/1']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/software/apps/:id" element={<AppDetail />} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('AppDetail', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders without throwing given a minimal app fixture', async () => {
    mockApi(minimalApp())
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My App')).toBeInTheDocument()
    })
  })
})
