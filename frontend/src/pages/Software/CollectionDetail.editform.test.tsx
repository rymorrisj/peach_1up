import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import { ToastProvider } from '@/ui/ToastProvider'
import CollectionDetail from '@/pages/Software/CollectionDetail'
import { apiFetch } from '@/api/client'
import { createMockLibraryItem } from '@/test/helpers'

// Field-level coverage for the edit form (EditForm.tsx) rendered inside
// CollectionDetail.tsx. Only "title" was exercised end-to-end before this
// file — see CollectionDetail.mutations.test.tsx's "Save" describe block.
// Locks down current inline behavior ahead of a later extraction, same
// mocking approach as CollectionDetail.mutations.test.tsx (mock apiFetch at
// the network boundary only).
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
    genres: [],
    developer: null,
    publisher: null,
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

const adminUser = {
  id: 1,
  name: 'Admin',
  is_owner: true,
  is_admin: true,
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
  method?: string
  respond: () => unknown
}

interface RecordedCall {
  url: string
  method: string
  body: unknown
}

// Same flexible URL/method-keyed mock as CollectionDetail.mutations.test.tsx —
// custom handlers are tried before the baseline defaults.
function setupApi(handlers: Handler[] = []): RecordedCall[] {
  const allHandlers: Handler[] = [
    ...handlers,
    { match: '/api/v1/auth/me', respond: () => adminUser },
    { match: '/api/v1/auth/refresh', respond: () => ({ user: adminUser }) },
    { match: '/api/v1/settings/library-defaults', respond: () => ({ delete_media_on_removal: false, delete_original_on_upload: false }) },
    { match: '/api/v1/settings', respond: () => ({ metadata_provider: 'thegamesdb' }) },
    { match: /settings\/(thegamesdb-api-key\/status|igdb-status)/, respond: () => ({ enabled: true }) },
    { match: '/api/v1/user-items', respond: () => [] },
    { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [] }) },
    { match: '/api/v1/environment-items', respond: () => [] },
    { match: '/api/v1/tags', respond: () => [] },
    { match: /^\/api\/v1\/restrictions\//, respond: () => ({ restricted_user_item_ids: [] }) },
    { match: /\/launches$/, respond: () => [] },
    { match: '/api/v1/filesystem/drives', respond: () => ({ drives: [] }) },
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

function renderPage(slug = 'doom') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[`/software/games/${slug}`]}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <Routes>
              <Route path="/software/games/:slug" element={<CollectionDetail />} />
            </Routes>
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

async function saveAndWait(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Save Changes' }))
  await waitFor(() => {
    expect(screen.getByText('Saved ✓')).toBeInTheDocument()
  })
}

describe('CollectionDetail edit form (field-level)', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('edits sort_title and sends it on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const input = screen.getByLabelText('Sort Title')
    await user.type(input, 'Doom, The')
    expect(input).toHaveValue('Doom, The')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ sort_title: 'Doom, The' })
  })

  it('edits description and sends it on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const textarea = screen.getByLabelText('Description')
    await user.type(textarea, 'A classic shooter.')
    expect(textarea).toHaveValue('A classic shooter.')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ description: 'A classic shooter.' })
  })

  it('edits publisher and sends it on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const input = screen.getByLabelText('Publisher')
    await user.type(input, 'id Software')
    expect(input).toHaveValue('id Software')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ publisher: 'id Software' })
  })

  it('edits category and sends it on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const input = screen.getByLabelText('Category (custom)')
    await user.type(input, 'Shooter')
    expect(input).toHaveValue('Shooter')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ category: 'Shooter' })
  })

  it('edits year and sends it as a parsed integer on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const input = screen.getByLabelText('Year')
    await user.clear(input)
    await user.type(input, '1995')
    expect(input).toHaveValue(1995)

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ year: 1995 })
  })

  it('edits content rating and sends it on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const select = screen.getByLabelText('Content Rating')
    await user.selectOptions(select, 'M')
    expect(select).toHaveValue('M')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ content_rating: 'M' })
  })

  it('edits the platform (environment_item_id) and sends it as a parsed integer on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: '/api/v1/environment-items', respond: () => [
        { id: 5, name: 'My DOS PC', era: 'dos', emulator_slug: 'dosbox-x', status: 'healthy', is_system: false, hardware_profile: 'standard' },
      ] },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const select = screen.getByLabelText('Platform')
    await user.selectOptions(select, '5')
    expect(select).toHaveValue('5')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ environment_item_id: 5 })
  })

  it('edits the launch profile (a matching-era option) and sends it as a parsed integer on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection() },
      { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [
        { id: 10, name: 'DOSBox Default', slug: 'dosbox-default', era: 'dos', emulator_slug: 'dosbox-x', is_bundled: true, enable_networking: false, enable_dgvoodoo2: false, use_drive: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      ] }) },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    const select = screen.getByLabelText('Launch Profile')
    await user.selectOptions(select, '10')
    expect(select).toHaveValue('10')
    expect(screen.queryByText('Selected profile targets a different era — launch may fail.')).not.toBeInTheDocument()

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
    expect(patch[0].body).toMatchObject({ profile_item_id: 10 })
  })

  describe('era change interactions (mismatch warning, profile grouping)', () => {
    const dosProfile = { id: 10, name: 'DOSBox Default', slug: 'dosbox-default', era: 'dos', emulator_slug: 'dosbox-x', is_bundled: true, enable_networking: false, enable_dgvoodoo2: false, use_drive: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }
    const win95Profile = { id: 20, name: 'Win95 Default', slug: 'win95-default', era: 'win95', emulator_slug: '86box', is_bundled: false, enable_networking: false, enable_dgvoodoo2: false, use_drive: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }

    it('groups profiles by era match and shows no mismatch warning while the era matches the assigned profile', async () => {
      setupApi([
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ era: 'dos', profile_item_id: 10 }) },
        { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [dosProfile, win95Profile] }) },
      ])
      renderPage()
      await waitForLoaded()

      // Matching-era profile renders without an era suffix; the other-era
      // profile is labeled with its own era so the "Other eras" optgroup
      // grouping in EditForm.tsx is distinguishable in the flattened option list.
      expect(screen.getByRole('option', { name: 'DOSBox Default (default)' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Win95 Default (Windows 95)' })).toBeInTheDocument()
      expect(screen.queryByText('Selected profile targets a different era — launch may fail.')).not.toBeInTheDocument()
    })

    it('shows the mismatch warning once the era is changed away from the assigned profile\'s era', async () => {
      const user = userEvent.setup()
      const calls = setupApi([
        { match: '/api/v1/game-item-bundle/by-slug/doom', method: 'GET', respond: () => fullCollection({ era: 'dos', profile_item_id: 10 }) },
        { match: /^\/api\/v1\/profile-items/, respond: () => ({ items: [dosProfile, win95Profile] }) },
        { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
        { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
      ])
      renderPage()
      await waitForLoaded()

      const eraSelect = screen.getByLabelText('Era')
      await user.selectOptions(eraSelect, 'win95')
      expect(eraSelect).toHaveValue('win95')

      expect(screen.getByText('Selected profile targets a different era — launch may fail.')).toBeInTheDocument()

      await saveAndWait(user)
      const patch = callsTo(calls, '/api/v1/game-item-bundle/1', 'PATCH')
      expect(patch[0].body).toMatchObject({ era: 'win95' })
    })
  })

  it('sets executable_path via the file browser and sends it on save', async () => {
    const user = userEvent.setup()
    const calls = setupApi([
      {
        match: '/api/v1/game-item-bundle/by-slug/doom',
        method: 'GET',
        respond: () => fullCollection({
          items: [
            { id: 100, game_item_bundle_id: 1, disc_number: 1, media_path: '/media/doom/disc1.iso', executable_path: null, cover_art_url: null },
          ],
        }),
      },
      {
        match: /^\/api\/v1\/filesystem\/browse/,
        respond: () => ({
          current_path: 'C:\\Games\\Doom',
          parent_path: null,
          dirs: [],
          files: [{ name: 'DOOM.EXE', path: 'C:\\Games\\Doom\\DOOM.EXE', size_bytes: 12345 }],
        }),
      },
      { match: '/api/v1/game-item-bundle/1', method: 'PATCH', respond: () => ({}) },
      { match: '/api/v1/game-item-bundle/1/items/100', method: 'PATCH', respond: () => ({}) },
    ])
    renderPage()
    await waitForLoaded()

    expect(screen.getByText('No launch file detected — browse to set one.')).toBeInTheDocument()

    // Two "Browse…" buttons exist (Cover Art Path uses the same PathInput
    // control) — the second one belongs to the Launch File field, rendered
    // just after Cover Art Path in EditForm.tsx.
    const browseButtons = screen.getAllByRole('button', { name: 'Browse…' })
    await user.click(browseButtons[1])
    await user.click(await screen.findByRole('button', { name: /DOOM\.EXE/ }))

    expect(screen.queryByText('No launch file detected — browse to set one.')).not.toBeInTheDocument()
    // The FileBrowser dialog stays mounted (just closed) after selection, so
    // "DOOM.EXE" also still matches inside its file listing — scope to the
    // Launch File display span via its title attribute (set to the full path).
    expect(screen.getByTitle('C:\\Games\\Doom\\DOOM.EXE')).toHaveTextContent('DOOM.EXE')

    await saveAndWait(user)
    const patch = callsTo(calls, '/api/v1/game-item-bundle/1/items/100', 'PATCH')
    expect(patch[0].body).toMatchObject({ executable_path: 'C:\\Games\\Doom\\DOOM.EXE' })
  })
})
