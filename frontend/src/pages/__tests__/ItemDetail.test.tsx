import { screen, waitFor } from '@testing-library/react'
import { render } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import ItemDetail from '@/pages/Library/ItemDetail'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type LibraryItemRead = components['schemas']['LibraryItemRead']
type ProfileRead = components['schemas']['ProfileRead']

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  setSessionToken: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, public readonly detail: string) {
      super(detail)
      this.name = 'ApiError'
    }
  },
}))

function makeItem(overrides: Partial<LibraryItemRead> = {}): LibraryItemRead {
  return {
    id: 1,
    title: 'Doom',
    era: 'dos',
    media_path: '/library/doom',
    launch_review_flagged: false,
    installed: true,
    requires_install: false,
    launch_count: 0,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    tags: [],
    slug: 'doom',
    profile_id: null,
    ...overrides,
  } as LibraryItemRead
}

const DOSBOX_PROFILE: ProfileRead = {
  id: 5,
  name: 'DOS Profile',
  slug: 'dos-profile',
  emulator_slug: 'dosbox-x',
  era: 'dos',
  is_bundled: true,
  enable_networking: false,
  enable_dgvoodoo2: false,
  use_drive: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
} as ProfileRead

const WIN95_PROFILE: ProfileRead = {
  id: 6,
  name: 'Windows 95 Profile',
  slug: 'win95-profile',
  emulator_slug: '86box',
  era: 'win95',
  is_bundled: true,
  enable_networking: false,
  enable_dgvoodoo2: false,
  use_drive: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
} as ProfileRead

function mockApi(item: LibraryItemRead, profiles: ProfileRead[]) {
  vi.mocked(apiFetch).mockImplementation((url) => {
    if (typeof url !== 'string') return Promise.resolve([])
    if (url === '/api/v1/auth/me') return Promise.reject(new ApiError(401, 'Not authenticated'))
    if (url === '/api/v1/library/by-slug/doom') return Promise.resolve(item)
    if (url === '/api/v1/profiles') return Promise.resolve(profiles)
    if (url === '/api/v1/platforms') return Promise.resolve([])
    if (url === `/api/v1/library/${item.id}/launches`) return Promise.resolve([])
    if (url === '/api/v1/launches') return Promise.resolve([])
    return Promise.resolve([])
  })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/library/doom']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/library/:slug" element={<ItemDetail />} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('ItemDetail launch button', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('is disabled and prompts for a profile when none is assigned', async () => {
    mockApi(makeItem({ profile_id: null }), [DOSBOX_PROFILE])
    renderPage()

    const launchBtn = await screen.findByRole('button', { name: 'Assign a profile to launch' })
    expect(launchBtn).toBeDisabled()
    expect(screen.getByText(/select a launch profile above to enable launch/i)).toBeInTheDocument()
  })

  it('is enabled when a valid launch profile is assigned', async () => {
    mockApi(makeItem({ profile_id: 5 }), [DOSBOX_PROFILE])
    renderPage()

    const launchBtn = await screen.findByRole('button', { name: 'Launch' })
    expect(launchBtn).toBeEnabled()
  })

  it('shows an era mismatch warning when the assigned profile targets a different emulator', async () => {
    // Item era is 'dos' (expects emulator 'dosbox-x' per ERA_TO_EMULATOR), but
    // the assigned profile (id 6) is an 86box/win95 profile.
    mockApi(makeItem({ profile_id: 6, era: 'dos' }), [DOSBOX_PROFILE, WIN95_PROFILE])
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/selected profile targets a different era/i)).toBeInTheDocument()
    })
    // Launch is still enabled — the mismatch is a warning, not a hard block.
    expect(screen.getByRole('button', { name: 'Launch' })).toBeEnabled()
  })
})
