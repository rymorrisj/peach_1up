import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import FirstRun from '@/pages/FirstRun'

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

// Owner already exists so the wizard starts on the Emulators step directly,
// this suite doesn't touch the Step0Owner/PIN flow.
function mockFirstRunApi() {
  vi.mocked(apiFetch).mockImplementation((path: string) => {
    if (path === '/api/v1/settings/first-run-status') {
      return Promise.resolve({
        first_run_complete: false,
        owner_exists: true,
        emulators: [],
        paths: {},
      }) as ReturnType<typeof apiFetch>
    }
    if (path === '/api/v1/settings/complete-first-run') {
      return Promise.resolve(undefined) as ReturnType<typeof apiFetch>
    }
    if (path.startsWith('/api/v1/bios')) {
      return Promise.resolve({ items: [], total: 0, limit: 200, offset: 0 }) as ReturnType<typeof apiFetch>
    }
    return Promise.resolve(undefined) as ReturnType<typeof apiFetch>
  })
}

function renderWizard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/first-run']}>
        <FirstRun />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('FirstRun wizard', () => {
  // jsdom's window.location.replace is non-configurable, so it can't be
  // spied on directly with vi.spyOn — replace the whole location object.
  let replaceSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    replaceSpy = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, replace: replaceSpy },
      writable: true,
      configurable: true,
    })
    mockFirstRunApi()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  it('starts on the Emulators step when the owner already exists', async () => {
    renderWizard()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Emulators' })).toBeInTheDocument()
    })
  })

  it('advances from Emulators to BIOS on Next', async () => {
    const user = userEvent.setup()
    renderWizard()
    await waitFor(() => screen.getByRole('button', { name: 'Next: BIOS' }))
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }))
    expect(screen.getByRole('heading', { name: 'BIOS Files' })).toBeInTheDocument()
  })

  it('returns from BIOS to Emulators on Back', async () => {
    const user = userEvent.setup()
    renderWizard()
    await waitFor(() => screen.getByRole('button', { name: 'Next: BIOS' }))
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }))
    await user.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('heading', { name: 'Emulators' })).toBeInTheDocument()
  })

  it('calls complete-first-run and redirects to / when Skip is clicked on the Emulators step', async () => {
    const user = userEvent.setup()
    renderWizard()
    await waitFor(() => screen.getByRole('button', { name: 'Skip setup' }))
    await user.click(screen.getByRole('button', { name: 'Skip setup' }))
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', { method: 'POST' })
    })
    expect(replaceSpy).toHaveBeenCalledWith('/')
  })

  it('calls complete-first-run and redirects to / when Finish is clicked on the BIOS step', async () => {
    const user = userEvent.setup()
    renderWizard()
    await waitFor(() => screen.getByRole('button', { name: 'Next: BIOS' }))
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }))
    await waitFor(() => screen.getByRole('button', { name: 'Finish' }))
    await user.click(screen.getByRole('button', { name: 'Finish' }))
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', { method: 'POST' })
    })
    expect(replaceSpy).toHaveBeenCalledWith('/')
  })

  it('calls complete-first-run and redirects to /emulators when the Emulators step finish-and-go button is clicked', async () => {
    const user = userEvent.setup()
    renderWizard()
    await waitFor(() => screen.getByRole('button', { name: 'Finish setup & go to Emulators →' }))
    await user.click(screen.getByRole('button', { name: 'Finish setup & go to Emulators →' }))
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', { method: 'POST' })
    })
    expect(replaceSpy).toHaveBeenCalledWith('/emulators')
  })

  it('calls complete-first-run and redirects to /emulators/bios when the BIOS step finish-and-go button is clicked', async () => {
    const user = userEvent.setup()
    renderWizard()
    await waitFor(() => screen.getByRole('button', { name: 'Next: BIOS' }))
    await user.click(screen.getByRole('button', { name: 'Next: BIOS' }))
    await waitFor(() => screen.getByRole('button', { name: 'Finish setup & go to BIOS →' }))
    await user.click(screen.getByRole('button', { name: 'Finish setup & go to BIOS →' }))
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/api/v1/settings/complete-first-run', { method: 'POST' })
    })
    expect(replaceSpy).toHaveBeenCalledWith('/emulators/bios')
  })
})
