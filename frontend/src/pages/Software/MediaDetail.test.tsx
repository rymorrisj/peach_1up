import { screen, waitFor, render } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import MediaDetail from '@/pages/Software/MediaDetail'
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

function minimalMedia(overrides?: Record<string, unknown>) {
  return {
    id: 1,
    slug: 'my-video',
    title: 'My Video',
    description: null,
    tags: [],
    media_kind: 'video',
    cover_art_path: null,
    cover_art_url: null,
    items: [
      { id: 100, media_item_bundle_id: 1, file_path: '/media/video.mp4', cover_art_path: null, cover_art_url: null },
    ],
    ...overrides,
  }
}

function mockApi(media: unknown) {
  vi.mocked(apiFetch).mockImplementation((url: unknown) => {
    if (typeof url !== 'string') return Promise.resolve([])
    if (url === '/api/v1/auth/me') return Promise.resolve(plainUser)
    if (url === '/api/v1/auth/refresh') return Promise.resolve({ user: plainUser })
    if (url === '/api/v1/media-item-bundle/1') return Promise.resolve(media)
    return Promise.resolve([])
  })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/software/media/1']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/software/media/:id" element={<MediaDetail />} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('MediaDetail', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders without throwing given a minimal media fixture', async () => {
    mockApi(minimalMedia())
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Video')).toBeInTheDocument()
    })
  })
})
