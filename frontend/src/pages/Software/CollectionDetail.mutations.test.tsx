import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import { ToastProvider } from '@/ui/ToastProvider'
import CollectionDetail from '@/pages/Software/CollectionDetail'
import { apiFetch, ApiError } from '@/api/client'
import { createMockLibraryItem } from '@/test/helpers'

// Mutation-path coverage, follow-up to the read-path pass (CollectionDetail.test.tsx).
// Same pattern: mock only apiFetch at the network boundary, single Route for
// useParams, no reference to routing.sectionRedirects.test.tsx.
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

// genres must always be overridden — CollectionDetail.tsx reads
// collection.genres.length with no null guard (see read-path pass finding).
function fullCollection(overrides?: Record<string, unknown>) {
  return createMockLibraryItem({
    id: 1,
    slug: 'doom',
    title: 'Doom',
    era: 'dos',
    launch_count: 5,
    launch_review_flagged: false,
    installed: true,
    requires_install: false,
    genres: ['Action', 'Shooter'],
    developer: 'id Software',
    publisher: 'id Software',
    content_rating: null,
    sort_title: null,
    description: null,
    category: null,
    year: 1993,
    delete_media_override: null,
    profile_item_id: null,
    last_launched_at: null,
    tags: [],
    ...overrides,
  })
}

function makeUser(overrides: Record<string, unknown>) {
  return {
    id: 2,
    name: 'Bob',
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
    ...overrides,
  }
}

const adminUser = makeUser({ id: 1, name: 'Admin', is_owner: true, is_admin: true })

interface Handler {
  match: string | RegExp
  method?: string
  respond: () => unknown
}

interface RecordedCall {
  url: string
  method: string
  body: unknown
}

// Flexible URL/method-keyed mock. Custom handlers (passed in) are tried
// before the baseline defaults, so a test can override any endpoint (e.g.
// make the collection fetch itself 404, or make one specific PATCH reject)
// without having to restate every other endpoint the page touches on mount.
function setupApi(user: unknown, handlers: Handler[] = []): RecordedCall[] {
  const allHandlers: Handler[] = [
    ...handlers,
    { match: '/api/v1/auth/me', respond: () => user },
    { match: '/api/v1/auth/refresh', respond: () => ({ user }) },
    { match: '/api/v1/settings/library-defaults', respond: () => ({ delete_media_on_removal: false, delete_original_on_upload: false }) },
    { match: '/api/v1/settings', respond: () => ({ metadata_provider: 'thegamesdb' }) },
    { match: /settings\/(thegamesdb-api-key\/status|igdb-status)/, respond: () => ({ enabled: true }) },
    { match: '/api/v1/user-items', respond: () => [] },
    { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [] }) },
    { match: '/api/v1/environment-items', respond: () => [] },
    { match: '/api/v1/tags', respond: () => [] },
    { match: /^\/api\/v1\/restrictions\//, respond: () => ({ restricted_user_item_ids: [] }) },
    { match: /\/launches$/, respond: () => [] },
  ]

  const calls: RecordedCall[] = []

  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = typeof url === 'string' ? url : ''
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    calls.push({ url: u, method, body })
    for (const h of allHandlers) {
      const matches = typeof h.match === 'string' ? u === h.match : h.match.test(u)
      if (matches && (!h.method || h.method === method)) {
        return Promise.resolve().then(h.respond)
      }
    }
    return Promise.resolve([])
  })

  return calls
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{location.pathname}</div>
}

function renderPage(slug = 'doom') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[`/software/games/${slug}`]}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <Routes>
              <Route path="/software/games/:slug" element={<CollectionDetail />} />
              <Route path="/software" element={<div>Software list</div>} />
            </Routes>
            <LocationProbe />
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

async function waitForLoaded() {
  await waitFor(() => {
    expect(screen.getByText('Doom')).toBeInTheDocument()
  })
}

function callsTo(calls: RecordedCall[], url: string, method: string) {
  return calls.filter((c) => c.url === url && c.method === method)
}

describe('CollectionDetail (mutation path)', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  // ── Save (bundle fields + always-on launch-disc executable_path patch) ──
  describe('Save', () => {
    it('saves edited fields and shows the success indicator', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await user.clear(screen.getByLabelText('Title'))
      await user.type(screen.getByLabelText('Title'), 'Doom II')
      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      await waitFor(() => {
        expect(screen.getByText('Saved ✓')).toBeInTheDocument()
      })

      const bundlePatch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
      expect(bundlePatch.length).toBeGreaterThanOrEqual(1)
      expect(bundlePatch[0].body).toMatchObject({ title: 'Doom II' })
      expect(callsTo(calls, '/api/v1/game-item-bundle/1/items/100', 'PATCH').length).toBe(1)
    })

    it('persists a staged disc reorder on save', async () => {
      const user = userEvent.setup()
      const items = [
        { id: 100, game_item_bundle_id: 1, disc_number: 1, file_path: '/media/doom/disc1.iso', executable_path: null, cover_art_path: null, cover_art_url: null, file_type: null, folder_path: null, detection_reason: null, file_size_bytes: null },
        { id: 200, game_item_bundle_id: 1, disc_number: 2, file_path: '/media/doom/disc2.iso', executable_path: null, cover_art_path: null, cover_art_url: null, file_type: null, folder_path: null, detection_reason: null, file_size_bytes: null },
      ]
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ items, launch_disk_id: 100, display_disk_id: 100 }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/items/reorder', method: 'PATCH', respond: () => ({}) },
        { match: /^\/api\/v1\/game-item-bundle\/1\/items\/\d+$/, method: 'PATCH', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Move disc1.iso down' }))
      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      await waitFor(() => {
        expect(screen.getByText('Saved ✓')).toBeInTheDocument()
      })

      const reorderCall = callsTo(calls, '/api/v1/game-item-bundle/1/items/reorder', 'PATCH')
      expect(reorderCall.length).toBe(1)
      expect(reorderCall[0].body).toEqual({ disc_order: [200, 100] })
    })

    it('surfaces a save error instead of failing silently', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => Promise.reject(new ApiError(400, 'Title cannot be blank.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Title cannot be blank.')
      })
      expect(screen.queryByText('Saved ✓')).not.toBeInTheDocument()
    })
  })

  // ── Installed toggle (confirm-gated) ──
  describe('Installed toggle', () => {
    it('marks the collection as not installed after confirming', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ installed: true }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Mark as not installed' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: 'Confirm' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Mark as installed' })).toBeInTheDocument()
      })
      expect(screen.getByText('○ No')).toBeInTheDocument()

      const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
      expect(patch.length).toBe(1)
      expect(patch[0].body).toEqual({ installed: false })
    })

    it('surfaces an error and leaves the label unchanged when the toggle fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ installed: true }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => Promise.reject(new ApiError(500, 'Update failed.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Mark as not installed' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: 'Confirm' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Update failed.')
      })
      expect(screen.getByRole('button', { name: 'Mark as not installed' })).toBeInTheDocument()
    })

    it('is hidden entirely for a non-DOS era', async () => {
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ era: 'win95', installed: true }) },
      ])
      renderPage()
      await waitForLoaded()

      expect(screen.queryByText('Installed:')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Mark as installed' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Mark as not installed' })).not.toBeInTheDocument()
    })
  })

  // ── Delete-media-on-removal override (immediate PATCH, no confirm) ──
  describe('Delete-media override toggle', () => {
    it('PATCHes immediately with no confirmation step', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ delete_media_override: null }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      await user.click(screen.getByRole('checkbox', { name: /delete all files\/folders/i }))

      await waitFor(() => {
        const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
        expect(patch.length).toBe(1)
        expect(patch[0].body).toEqual({ delete_media_override: true })
      })
    })

    it('surfaces an error when the toggle fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ delete_media_override: null }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => Promise.reject(new ApiError(500, 'Failed to update.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('checkbox', { name: /delete all files\/folders/i }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Failed to update.')
      })
    })
  })

  // ── Delete collection (destructive; two-step confirmation-token flow) ──
  describe('Delete collection', () => {
    it('issues a confirmation token, then deletes with it, then navigates away', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/confirm-delete', method: 'POST', respond: () => ({ confirmation_token: 'tok-123' }) },
        { match: /^\/api\/v1\/game-item-bundle\/1\?confirmation_token=tok-123$/, method: 'DELETE', respond: () => undefined },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Delete this collection' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: 'Confirm' }))

      await waitFor(() => {
        expect(screen.getByTestId('location-probe')).toHaveTextContent('/software')
      })

      // Two distinct calls, in order — not collapsed into one.
      const patchIdx = calls.findIndex((c) => c.url === '/api/v1/game-item-bundle/1' && c.method === 'PATCH' && 'delete_media_override' in (c.body as object))
      const issueIdx = calls.findIndex((c) => c.url === '/api/v1/game-item-bundle/1/confirm-delete' && c.method === 'POST')
      const deleteIdx = calls.findIndex((c) => c.url.startsWith('/api/v1/game-item-bundle/1?confirmation_token=') && c.method === 'DELETE')
      expect(patchIdx).toBeGreaterThanOrEqual(0)
      expect(issueIdx).toBeGreaterThan(patchIdx)
      expect(deleteIdx).toBeGreaterThan(issueIdx)
    })

    it('surfaces an error and does not navigate when issuing the confirmation token fails', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/confirm-delete', method: 'POST', respond: () => Promise.reject(new ApiError(500, 'Could not start delete.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Delete this collection' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: 'Confirm' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Could not start delete.')
      })
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/software/games/doom')
      expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    })

    it('surfaces an error and does not navigate when the confirmation token is rejected/expired at delete time', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/confirm-delete', method: 'POST', respond: () => ({ confirmation_token: 'tok-expired' }) },
        { match: /^\/api\/v1\/game-item-bundle\/1\?confirmation_token=tok-expired$/, method: 'DELETE', respond: () => Promise.reject(new ApiError(400, 'Confirmation token expired.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Delete this collection' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: 'Confirm' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Confirmation token expired.')
      })
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/software/games/doom')

      // Both steps ran as two distinct calls — the failure was in the second
      // (delete), not a fallback that skipped straight there.
      expect(calls.some((c) => c.url === '/api/v1/game-item-bundle/1/confirm-delete' && c.method === 'POST')).toBe(true)
      expect(calls.some((c) => c.url.startsWith('/api/v1/game-item-bundle/1?confirmation_token=') && c.method === 'DELETE')).toBe(true)
    })

    it('sends the checkbox value the user toggled in the dialog, not the default', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ delete_media_override: null }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/confirm-delete', method: 'POST', respond: () => ({ confirmation_token: 'tok-456' }) },
        { match: /^\/api\/v1\/game-item-bundle\/1\?confirmation_token=tok-456$/, method: 'DELETE', respond: () => undefined },
      ])
      renderPage()
      await waitForLoaded()

      // delete_media_override is null and library-defaults' delete_media_on_removal
      // is false (setupApi's baseline), so resolvedDeleteMedia — the checkbox's
      // defaultChecked — is false. Toggle it on before confirming.
      await user.click(screen.getByRole('button', { name: 'Delete this collection' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
      const checkbox = screen.getByRole('checkbox', { name: /also delete media files from disk/i })
      expect(checkbox).not.toBeChecked()
      await user.click(checkbox)
      await user.click(screen.getByRole('button', { name: 'Confirm' }))

      await waitFor(() => {
        expect(screen.getByTestId('location-probe')).toHaveTextContent('/software')
      })

      const patch = calls.find((c) => c.url === '/api/v1/game-item-bundle/1' && c.method === 'PATCH' && 'delete_media_override' in (c.body as object))
      expect(patch?.body).toEqual({ delete_media_override: true })
    })
  })

  // ── Flag launch ──
  describe('Flag launch', () => {
    it('flags the launch for review', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1/flag-launch', method: 'POST', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Advanced' }))
      await user.click(screen.getByRole('button', { name: 'Flag broken launch' }))

      await waitFor(() => {
        expect(callsTo(calls, '/api/v1/game-item-bundle/1/flag-launch', 'POST').length).toBe(1)
      })
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('surfaces an error when flagging fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/game-item-bundle/1/flag-launch', method: 'POST', respond: () => Promise.reject(new ApiError(500, 'Failed to flag.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Advanced' }))
      await user.click(screen.getByRole('button', { name: 'Flag broken launch' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Failed to flag.')
      })
    })
  })

  // ── Tag remove / assign ──
  describe('Tags', () => {
    const tag = { id: 9, name: 'Favorite', color: 'coral', item_count: 1, is_system: false }

    it('removes an assigned tag', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ tags: [tag] }) },
        { match: /^\/api\/v1\/tags\/9\/assignments$/, method: 'DELETE', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Remove tag Favorite' }))

      await waitFor(() => {
        const del = callsTo(calls, '/api/v1/tags/9/assignments', 'DELETE')
        expect(del.length).toBe(1)
        expect(del[0].body).toEqual({ entity_type: 'game_item_bundle', entity_id: 1 })
      })
    })

    it('surfaces an error when tag removal fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ tags: [tag] }) },
        { match: /^\/api\/v1\/tags\/9\/assignments$/, method: 'DELETE', respond: () => Promise.reject(new ApiError(500, 'Failed to remove tag.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Remove tag Favorite' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Failed to remove tag.')
      })
    })

    it('assigns a tag selected from the combobox', async () => {
      const user = userEvent.setup()
      const otherTag = { id: 10, name: 'Speedrun', color: 'sky', item_count: 0, is_system: false }
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ tags: [] }) },
        { match: '/api/v1/tags', respond: () => [otherTag] },
        { match: /^\/api\/v1\/tags\/10\/assignments$/, method: 'POST', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      const combobox = screen.getByPlaceholderText('Search tags…')
      await user.click(combobox)
      await user.type(combobox, 'Speed')
      await user.click(await screen.findByText('Speedrun'))

      await waitFor(() => {
        const post = callsTo(calls, '/api/v1/tags/10/assignments', 'POST')
        expect(post.length).toBe(1)
        expect(post[0].body).toEqual({ entity_type: 'game_item_bundle', entity_id: 1 })
      })
    })

    it('surfaces an error when tag assignment fails', async () => {
      const user = userEvent.setup()
      const otherTag = { id: 10, name: 'Speedrun', color: 'sky', item_count: 0, is_system: false }
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ tags: [] }) },
        { match: '/api/v1/tags', respond: () => [otherTag] },
        { match: /^\/api\/v1\/tags\/10\/assignments$/, method: 'POST', respond: () => Promise.reject(new ApiError(500, 'Failed to add tag.')) },
      ])
      renderPage()
      await waitForLoaded()

      const combobox = screen.getByPlaceholderText('Search tags…')
      await user.click(combobox)
      await user.type(combobox, 'Speed')
      await user.click(await screen.findByText('Speedrun'))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Failed to add tag.')
      })
    })
  })

  // ── Restrictions save ──
  describe('Restrictions save', () => {
    it('saves the toggled restriction set', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/user-items', respond: () => [makeUser({ id: 2, name: 'Bob', is_owner: false })] },
        { match: '/api/v1/restrictions/game/1', method: 'GET', respond: () => ({ restricted_user_item_ids: [] }) },
        { match: '/api/v1/restrictions/game/1', method: 'PUT', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeInTheDocument())
      await user.click(screen.getByRole('checkbox', { name: 'Bob' }))
      await user.click(screen.getByRole('button', { name: 'Save Restrictions' }))

      await waitFor(() => {
        const put = calls.filter((c) => c.url === '/api/v1/restrictions/game/1' && c.method === 'PUT')
        expect(put.length).toBe(1)
        expect(put[0].body).toEqual({ user_item_ids: [2] })
      })
    })

    it('surfaces an error when saving restrictions fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
        { match: '/api/v1/user-items', respond: () => [makeUser({ id: 2, name: 'Bob', is_owner: false })] },
        { match: '/api/v1/restrictions/game/1', method: 'GET', respond: () => ({ restricted_user_item_ids: [] }) },
        { match: '/api/v1/restrictions/game/1', method: 'PUT', respond: () => Promise.reject(new ApiError(500, 'Failed to save restrictions.')) },
      ])
      renderPage()
      await waitForLoaded()

      await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Bob' })).toBeInTheDocument())
      await user.click(screen.getByRole('checkbox', { name: 'Bob' }))
      await user.click(screen.getByRole('button', { name: 'Save Restrictions' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Failed to save restrictions.')
      })
    })
  })

  // ── Launch gating (backend-driven) ──
  // Launch gating is now driven solely by the backend-computed
  // launch_blocked_reason on the bundle (see launchGateFromReason in
  // Software/types.ts), not the old client-side hasProfile check. A bundle with
  // no profile is returned by the backend with launch_blocked_reason:
  // "no_profile", which disables the button and shows the assign-a-profile note.
  describe('Profile-gated launch', () => {
    it('disables launch and shows the assign-a-profile note when the backend reports no_profile', async () => {
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ profile_item_id: null, launch_blocked_reason: 'no_profile' }) },
      ])
      renderPage()
      await waitForLoaded()

      const launchButton = screen.getByRole('button', { name: 'Assign a profile to launch' })
      expect(launchButton).toBeDisabled()
      expect(screen.getByText('Assign a launch profile to enable launch.')).toBeInTheDocument()
    })

    it('launches with the assigned profile when one is set', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ profile_item_id: 5 }) },
        { match: '/api/v1/game-item-bundle/1/launch', method: 'POST', respond: () => ({ launch_history_id: 999, warnings: [] }) },
      ])
      renderPage()
      await waitForLoaded()

      const launchButton = screen.getByRole('button', { name: 'Launch' })
      expect(launchButton).toBeEnabled()
      await user.click(launchButton)

      await waitFor(() => {
        expect(screen.getByText('Launch started. The emulator should open shortly.')).toBeInTheDocument()
      })
      const launchCalls = callsTo(calls, '/api/v1/game-item-bundle/1/launch', 'POST')
      expect(launchCalls.length).toBe(1)
      expect(launchCalls[0].body).toEqual({ profile_item_id: 5 })
    })

    it('surfaces an error when launch fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ profile_item_id: 5 }) },
        { match: '/api/v1/game-item-bundle/1/launch', method: 'POST', respond: () => Promise.reject(new ApiError(500, 'Launch failed badly.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Launch' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Launch failed badly.')
      })
    })
  })

  // ── Xiso convert (surfaced only after a launch fails with error_type 'xbox_dvd_rip') ──
  describe('Xiso convert', () => {
    async function triggerXboxDvdRipError(user: ReturnType<typeof userEvent.setup>, calls: RecordedCall[]) {
      await user.click(screen.getByRole('button', { name: 'Launch' }))
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Convert with extract-xiso' })).toBeInTheDocument()
      })
      return calls
    }

    it('starts a conversion after an xbox_dvd_rip launch failure', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ profile_item_id: 5 }) },
        {
          match: '/api/v1/game-item-bundle/1/launch',
          method: 'POST',
          respond: () => Promise.reject(new ApiError(422, 'Xbox DVD rip detected', { error_type: 'xbox_dvd_rip', message: 'Xbox DVD rip detected' })),
        },
        { match: '/api/v1/game-item-bundle/1/convert-xiso', method: 'POST', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()
      await triggerXboxDvdRipError(user, calls)

      await user.click(screen.getByRole('button', { name: 'Convert with extract-xiso' }))

      await waitFor(() => {
        expect(callsTo(calls, '/api/v1/game-item-bundle/1/convert-xiso', 'POST').length).toBe(1)
      })
      expect(screen.getByText(/Converting… this can take a while/i)).toBeInTheDocument()
    })

    it('surfaces an error when starting the conversion fails', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ profile_item_id: 5 }) },
        {
          match: '/api/v1/game-item-bundle/1/launch',
          method: 'POST',
          respond: () => Promise.reject(new ApiError(422, 'Xbox DVD rip detected', { error_type: 'xbox_dvd_rip', message: 'Xbox DVD rip detected' })),
        },
        { match: '/api/v1/game-item-bundle/1/convert-xiso', method: 'POST', respond: () => Promise.reject(new ApiError(500, 'Failed to start conversion.')) },
      ])
      renderPage()
      await waitForLoaded()
      await triggerXboxDvdRipError(user, calls)

      await user.click(screen.getByRole('button', { name: 'Convert with extract-xiso' }))

      await waitFor(() => {
        expect(screen.getByText('Failed to start conversion.')).toBeInTheDocument()
      })
    })
  })

  // ── Fetch Metadata (collection-level enrichment wizard) ──
  describe('Fetch metadata', () => {
    const searchResult = { game_id: 501, title: 'Doom (1993)', release_date: '1993-12-10' }
    const details = {
      game_id: 501,
      title: 'Doom (1993)',
      release_date: '1993-12-10',
      overview: 'A classic.',
      rating: null,
      cover_art_url: null,
      cover_art_thumb_url: null,
      genres: ['Action'],
      developer: 'id Software',
      publisher: 'id Software',
    }

    it('searches, selects a match, fetches details, and applies them', async () => {
      const user = userEvent.setup()
      const calls = setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ content_rating: null }) },
        { match: /^\/api\/v1\/game-items\/metadata-search/, respond: () => ({ results: [searchResult] }) },
        { match: /^\/api\/v1\/game-items\/metadata-details/, respond: () => details },
        { match: '/api/v1/game-items/enrich', method: 'POST', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Fetch Metadata' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

      await user.click(screen.getByRole('button', { name: 'Search' }))
      await user.click(await screen.findByRole('radio'))
      await user.click(screen.getByRole('button', { name: 'Fetch Now' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Keep' })).toBeEnabled()
      })
      await user.click(screen.getByRole('button', { name: 'Keep' }))

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })

      const enrichCalls = callsTo(calls, '/api/v1/game-items/enrich', 'POST')
      expect(enrichCalls.length).toBe(1)
      expect(enrichCalls[0].body).toMatchObject({
        entity_type: 'game_item_bundle',
        entity_id: 1,
        metadata_source: 'TheGamesDB',
        title: 'Doom (1993)',
        developer: 'id Software',
        publisher: 'id Software',
      })
    })

    it('surfaces an error and keeps the modal open when applying metadata fails', async () => {
      const user = userEvent.setup()
      setupApi(adminUser, [
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ content_rating: null }) },
        { match: /^\/api\/v1\/game-items\/metadata-search/, respond: () => ({ results: [searchResult] }) },
        { match: /^\/api\/v1\/game-items\/metadata-details/, respond: () => details },
        { match: '/api/v1/game-items/enrich', method: 'POST', respond: () => Promise.reject(new Error('Enrich failed.')) },
      ])
      renderPage()
      await waitForLoaded()

      await user.click(screen.getByRole('button', { name: 'Fetch Metadata' }))
      await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

      await user.click(screen.getByRole('button', { name: 'Search' }))
      await user.click(await screen.findByRole('radio'))
      await user.click(screen.getByRole('button', { name: 'Fetch Now' }))
      await waitFor(() => expect(screen.getByRole('button', { name: 'Keep' })).toBeEnabled())
      await user.click(screen.getByRole('button', { name: 'Keep' }))

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('Enrich failed.')
      })
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })
})
