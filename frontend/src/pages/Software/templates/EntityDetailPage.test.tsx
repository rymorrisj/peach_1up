import { screen, waitFor, render } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import { apiFetch } from '@/api/client'
import { EntityDetailPage } from './EntityDetailPage'
import { gameDomainConfig } from '../configs/gameConfig'
import { appDomainConfig } from '../configs/appConfig'
import { mediaDomainConfig } from '../configs/mediaConfig'

// Basic smoke coverage for the shared template: it must render for each
// domain config without throwing, and configs that don't declare
// renderExtras (App, Media) must render exactly as before this file grew
// the slot mechanism, no game-only content leaking through. Not exhaustive
// behavior coverage, that's CollectionDetail*.test.tsx's job for Game.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    detail: string
    rawDetail: unknown
    constructor(status: number, detail: string, rawDetail?: unknown) {
      super(detail)
      this.status = status
      this.detail = detail
      this.rawDetail = rawDetail
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

interface Handler {
  match: string | RegExp
  respond: () => unknown
}

function mockApi(handlers: Handler[]) {
  const allHandlers: Handler[] = [
    ...handlers,
    { match: '/api/v1/auth/me', respond: () => plainUser },
    { match: '/api/v1/auth/refresh', respond: () => ({ user: plainUser }) },
  ]
  vi.mocked(apiFetch).mockImplementation((url: unknown) => {
    const u = typeof url === 'string' ? url : ''
    for (const h of allHandlers) {
      const matches = typeof h.match === 'string' ? u === h.match : h.match.test(u)
      if (matches) return Promise.resolve().then(h.respond)
    }
    return Promise.resolve([])
  })
}

function renderAt(path: string, routePattern: string, element: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path={routePattern} element={element} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('EntityDetailPage', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders for gameConfig without throwing', async () => {
    mockApi([
      {
        match: '/api/v1/game-item-bundle/by-slug/doom-test',
        respond: () => ({
          id: 1, slug: 'doom-test', title: 'Doom Test', description: null, tags: [],
          sort_title: null, era: 'dos', category: null, publisher: null, developer: null,
          genres: [], year: null, external_game_id: null, metadata_source: null,
          content_rating: null, launch_commands: null, installed: false, requires_install: false,
          launch_review_flagged: false, delete_media_override: null, environment_item_id: null,
          profile_item_id: null, drive_id: null, launch_disk_id: 100, display_disk_id: 100,
          last_launched_at: null, launch_count: 0,
          items: [{ id: 100, software_collection_id: 1, disc_number: 1, media_path: '/games/doom/disc1.iso', executable_path: null, cover_art_path: null, cover_art_url: null, media_type: null, folder_path: null, detection_reason: null, file_size_bytes: null }],
        }),
      },
      { match: '/api/v1/settings/library-defaults', respond: () => ({ delete_media_on_removal: false, delete_original_on_upload: false }) },
      { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [] }) },
      { match: '/api/v1/environment-items', respond: () => [] },
    ])
    renderAt('/software/games/doom-test', '/software/games/:slug', <EntityDetailPage config={gameDomainConfig} />)

    await waitFor(() => {
      expect(screen.getByText('Doom Test')).toBeInTheDocument()
    })
  })

  it('renders for appConfig without throwing, and app-only content stays absent (no renderExtras declared)', async () => {
    mockApi([
      {
        match: '/api/v1/app-item-bundle/1',
        respond: () => ({
          id: 1, slug: 'my-app', title: 'My App', description: null, tags: [],
          is_pc: true, category: null, publisher: null, developer: null, year: null,
          installed: false, environment_item_id: null, profile_item_id: null,
          launch_disk_id: 100, display_disk_id: 100, last_launched_at: null, launch_count: 0,
          items: [{ id: 100, app_item_bundle_id: 1, file_path: '/apps/myapp.exe', executable_path: null, cover_art_path: null, cover_art_url: null }],
        }),
      },
    ])
    renderAt('/software/apps/1', '/software/apps/:id', <EntityDetailPage config={appDomainConfig} />)

    await waitFor(() => {
      expect(screen.getByText('My App')).toBeInTheDocument()
    })
    // Slot mechanism no-ops for a config with no renderExtras: no game-only
    // sections (edit form, advanced/launch_commands) leak through.
    expect(screen.queryByRole('button', { name: 'Save Changes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Advanced' })).not.toBeInTheDocument()
    // The shared launch section (one of the four generic pieces) still works.
    expect(screen.getByRole('button', { name: /launch/i })).toBeInTheDocument()
  })

  it('renders for mediaConfig without throwing, and media-only/launch content stays absent (no renderExtras, no launchTargetType)', async () => {
    mockApi([
      {
        match: '/api/v1/media-item-bundle/1',
        respond: () => ({
          id: 1, slug: 'my-video', title: 'My Video', description: null, tags: [],
          media_kind: 'video', cover_art_path: null, cover_art_url: null,
          items: [{ id: 100, media_item_bundle_id: 1, file_path: '/media/video.mp4', cover_art_path: null, cover_art_url: null }],
        }),
      },
    ])
    renderAt('/software/media/1', '/software/media/:id', <EntityDetailPage config={mediaDomainConfig} />)

    await waitFor(() => {
      expect(screen.getByText('My Video')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'Save Changes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Advanced' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /launch/i })).not.toBeInTheDocument()
  })
})
