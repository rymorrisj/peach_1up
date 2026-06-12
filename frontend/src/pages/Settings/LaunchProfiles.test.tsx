import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'

// NOTE: the spec for this file referenced `src/components/...`, but the
// "Launch Profiles" UI actually lives at `src/pages/Settings/LaunchProfiles.tsx`.
// Importing it from its real location below.
import LaunchProfiles from '@/pages/Settings/LaunchProfiles'

type ProfileRead = components['schemas']['ProfileRead']
type CatalogEntryResponse = components['schemas']['CatalogEntryResponse']

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  setSessionToken: vi.fn(),
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

const EMULATOR: CatalogEntryResponse = {
  slug: 'dosbox-x',
  name: 'DOSBox-X',
  version: '1.0',
  description: 'DOS emulator',
  license: 'GPL',
  install_type: 'bundled',
  required: true,
} as CatalogEntryResponse

const PROFILE_WITH_LAUNCH_COMMANDS: ProfileRead = {
  id: 1,
  name: 'DOS Game',
  slug: 'dos-game',
  emulator_slug: 'dosbox-x',
  era: 'dos',
  is_bundled: false,
  enable_networking: false,
  enable_dgvoodoo2: false,
  use_drive: false,
  notes: null,
  extra_args: null,
  drive_slug: null,
  container_enabled: null,
  launch_commands: ['mount c c:\\game', 'c:\\game\\game.exe'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
} as ProfileRead

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <LaunchProfiles />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('LaunchProfiles submit payload', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('preserves an existing profile launch_commands on save', async () => {
    const user = userEvent.setup()
    let patchBody: Record<string, unknown> | null = null

    vi.mocked(apiFetch).mockImplementation((url, init) => {
      if (url === '/api/v1/profiles' && (!init || init.method === undefined)) {
        return Promise.resolve([PROFILE_WITH_LAUNCH_COMMANDS])
      }
      if (url === '/api/v1/drives') return Promise.resolve([])
      if (url === '/api/v1/emulators') return Promise.resolve([EMULATOR])
      if (url === '/api/v1/profiles/dos-game' && init?.method === 'PATCH') {
        patchBody = JSON.parse(init.body as string)
        return Promise.resolve(PROFILE_WITH_LAUNCH_COMMANDS)
      }
      return Promise.resolve([])
    })

    renderPage()

    await waitFor(() => expect(screen.getByText('DOS Game')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Edit' }))

    const dialog = screen.getByRole('dialog')
    await waitFor(() => expect(within(dialog).getByDisplayValue('DOS Game')).toBeInTheDocument())

    await user.click(within(dialog).getByRole('button', { name: 'Save Changes' }))

    await waitFor(() => expect(patchBody).not.toBeNull())

    expect((patchBody as unknown as Record<string, unknown>).launch_commands).toEqual(
      PROFILE_WITH_LAUNCH_COMMANDS.launch_commands,
    )
  })

  it('omits launch_commands from the create payload when none are configured', async () => {
    const user = userEvent.setup()
    let postBody: Record<string, unknown> | null = null

    vi.mocked(apiFetch).mockImplementation((url, init) => {
      if (url === '/api/v1/profiles' && init?.method === 'POST') {
        postBody = JSON.parse(init.body as string)
        return Promise.resolve(PROFILE_WITH_LAUNCH_COMMANDS)
      }
      if (url === '/api/v1/profiles') return Promise.resolve([])
      if (url === '/api/v1/drives') return Promise.resolve([])
      if (url === '/api/v1/emulators') return Promise.resolve([EMULATOR])
      return Promise.resolve([])
    })

    renderPage()

    await waitFor(() => expect(screen.getByText(/no launch profiles/i)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '+ Add Profile' }))

    // The <dialog> for the modal isn't reported as "open" by jsdom, so
    // role-based queries need `hidden: true` to see into it.
    const heading = await screen.findByRole('heading', { name: 'Add Launch Profile', hidden: true })
    const dialog = heading.closest('dialog') as HTMLElement
    await user.type(within(dialog).getByLabelText(/^Name/), 'New Profile')
    await user.selectOptions(within(dialog).getByLabelText(/^Emulator/), 'dosbox-x')
    // win95 (not dos/win31) keeps drive_mode at its 'none' default, avoiding
    // a second apiFetch('/api/v1/drives', { method: 'POST' }) call.
    await user.selectOptions(within(dialog).getByLabelText(/^Era/), 'win95')

    await user.click(within(dialog).getByRole('button', { name: 'Add Profile', hidden: true }))

    await waitFor(() => expect(postBody).not.toBeNull())

    // EMPTY_FORM defaults launch_commands to [], but handleSubmit() never
    // adds the key to the request body at all — so for the "no commands
    // configured" case the field is simply absent (rather than sent as []).
    expect((postBody as unknown as Record<string, unknown>).launch_commands).toBeUndefined()
  })
})
