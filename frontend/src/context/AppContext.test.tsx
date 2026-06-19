import { screen, waitFor } from '@testing-library/react'
import { render } from '@testing-library/react'
import { AppProvider } from '@/context/AppContext'
import { useAppContext } from '@/context/useAppContext'
import { apiFetch, ApiError } from '@/api/client'
import type { components } from '@shared/types'

type UserRead = components['schemas']['UserRead']

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

const OWNER: UserRead = {
  id: 1,
  name: 'Owner',
  is_owner: true,
  pin_required: false,
  can_launch_media: true,
  can_edit_platforms: true,
  can_edit_library: true,
  can_manage_profiles: true,
  can_edit_settings: true,
  is_admin: true,
  block_unrated_media: false,
  is_locked: false,
  failed_pin_attempts: 0,
  created_at: '2024-01-01T00:00:00Z',
} as UserRead

function Probe() {
  const { state } = useAppContext()
  return (
    <div>
      <div data-testid="active-user">{state.activeUser ? state.activeUser.name : 'none'}</div>
      <div data-testid="show-unauth-modal">{String(state.showUnauthModal)}</div>
    </div>
  )
}

function renderProbe() {
  return render(
    <AppProvider>
      <Probe />
    </AppProvider>,
  )
}

describe('AppContext initial auth check', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('sets the active user in context after a successful /api/v1/auth/me response', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (url === '/api/v1/auth/me') return Promise.resolve(OWNER)
      if (url === '/api/v1/auth/refresh') return Promise.resolve({ user: OWNER })
      return Promise.resolve([])
    })

    renderProbe()

    await waitFor(() => {
      expect(screen.getByTestId('active-user')).toHaveTextContent('Owner')
    })
    expect(screen.getByTestId('show-unauth-modal')).toHaveTextContent('false')
  })

  it('clears the active user and shows the unauth modal on a 401 from /api/v1/auth/me', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (url === '/api/v1/auth/me') return Promise.reject(new ApiError(401, 'Not authenticated'))
      return Promise.resolve([])
    })

    renderProbe()

    await waitFor(() => {
      expect(screen.getByTestId('show-unauth-modal')).toHaveTextContent('true')
    })
    expect(screen.getByTestId('active-user')).toHaveTextContent('none')
  })
})

// Note: the spec for this file also asked for a case covering a redirect to
// "/setup" when first_run_complete is false. That logic is not part of
// AppContext — it lives in the unexported `FirstRunGuard` component in
// src/main.tsx, which queries GET /api/v1/settings/first-run-status and
// redirects to "/first-run" (not "/setup") via <Navigate>. Since
// FirstRunGuard isn't exported and AppContext/AppProvider has no
// first-run-related state or behavior, that case isn't testable from this
// file and is omitted rather than fabricated.
