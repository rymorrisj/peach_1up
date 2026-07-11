/**
 * Integration tests for the route shape introduced by
 * dev_docs/v2/08_emulator_profiles_navigation.md — redirects, the
 * `/emulators/:slug` exception, and the promoted-Profiles no-`:slug`-route
 * fix, exercised against the real page/route-array exports main.tsx wires up.
 *
 * main.tsx itself is not imported: it self-mounts into `document.getElementById('root')`
 * as a module side effect (`ReactDOM.createRoot(...).render(...)`) and is wrapped
 * in FirstRunGuard/RequireAuth, which are orthogonal to this doc's routing shape.
 * Instead this file reconstructs the same nesting from the same building blocks
 * main.tsx consumes (`Software`+`softwareTabRoutes`, `Emulators`+`emulatorsTabRoutes`,
 * `System`+`systemTabRoutes`, `CollectionDetail`, `EmulatorDetail`, and the explicit
 * `/platform-health` redirect) — verified against main.tsx's actual route
 * declarations (read directly, not assumed from the doc's prose) before writing
 * this file.
 */
import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import Software, { softwareTabRoutes } from '@/pages/Software'
import CollectionDetail from '@/pages/Software/CollectionDetail'
import Emulators, { emulatorsTabRoutes } from '@/pages/Emulators'
import EmulatorDetail from '@/pages/Emulators/EmulatorDetail'
import System, { systemTabRoutes } from '@/pages/System'
import NotFound from '@/pages/NotFound'
import { apiFetch } from '@/api/client'

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

function mockApiGenerically() {
  // Every page mounted below fires several read-only queries on load. None of
  // these tests assert on fetched data — only on which component/route ends
  // up mounted — so a blanket empty-collection fallback (matching the pattern
  // already used by Software/index.test.tsx and Emulators/index.test.tsx) is
  // sufficient and keeps this file focused on routing, not fixtures.
  vi.mocked(apiFetch).mockResolvedValue([])
}

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location-display">{location.pathname}</div>
}

function renderAt(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/software" element={<Software />}>
              {softwareTabRoutes}
            </Route>
            <Route path="/software/games/:slug" element={<CollectionDetail />} />
            <Route path="/emulators" element={<Emulators />}>
              {emulatorsTabRoutes}
            </Route>
            <Route path="/emulators/:slug" element={<EmulatorDetail />} />
            <Route path="/system" element={<System />}>
              {systemTabRoutes}
            </Route>
            <Route path="/platform-health" element={<Navigate to="/system/health" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
          <LocationDisplay />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

async function expectFinalPath(path: string) {
  await waitFor(() => {
    expect(screen.getByTestId('location-display')).toHaveTextContent(path)
  })
}

describe('Section redirects (dev_docs/v2/08_emulator_profiles_navigation.md)', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('/platform-health redirects to /system/health (legacy link preserved)', async () => {
    mockApiGenerically()
    renderAt('/platform-health')
    await expectFinalPath('/system/health')
    // Confirms the target actually mounted System's Health tab, not just a URL change.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /health check all/i })).toBeInTheDocument()
    })
  })

  it('/system redirects to /system/health (default-tab convention)', async () => {
    mockApiGenerically()
    renderAt('/system')
    await expectFinalPath('/system/health')
  })

  it('/emulators redirects to /emulators/emulators (default-tab convention)', async () => {
    mockApiGenerically()
    renderAt('/emulators')
    await expectFinalPath('/emulators/emulators')
    // The default tab is the existing, unchanged Emulators list.
    await waitFor(() => {
      expect(screen.getByText(/no emulators found/i)).toBeInTheDocument()
    })
  })

  it('/software redirects to /software/games — confirmed as the actual default tab from Software/index.tsx, not assumed', async () => {
    mockApiGenerically()
    renderAt('/software')
    await expectFinalPath('/software/games')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /your software library is empty/i })).toBeInTheDocument()
    })
  })
})

describe('/emulators/:slug exception (Locked decision 13) — static tab segments resolve first', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it.each([
    ['/emulators/emulators', /no emulators found/i],
    ['/emulators/bios', /no bios requirements/i],
    ['/emulators/rom-packs', /no rom packs/i],
    ['/emulators/profiles', /no launch profiles/i],
  ] as const)('%s resolves to the static tab, not the /:slug dynamic route', async (segmentPath, marker) => {
    mockApiGenerically()
    renderAt(segmentPath)
    await expectFinalPath(segmentPath)
    await waitFor(() => {
      expect(screen.getByText(marker)).toBeInTheDocument()
    })
    // If the dynamic route had swallowed this path, EmulatorDetail would render
    // an <h1> falling back to the raw slug text (e.g. "bios") instead.
    expect(screen.queryByText('bios', { selector: 'h1' })).not.toBeInTheDocument()
  })

  it('/emulators/:slug still resolves to EmulatorDetail for a real (non-reserved) slug', async () => {
    mockApiGenerically()
    renderAt('/emulators/dosbox-x')
    await expectFinalPath('/emulators/dosbox-x')
    // EmulatorDetail's heading falls back to the raw slug when the catalog
    // entry isn't found in `entry?.name ?? slug` — a reliable, page-specific
    // marker that this is EmulatorDetail and not NotFound or a tab route.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'dosbox-x' })).toBeInTheDocument()
    })
  })
})

describe('Profiles has no per-profile route (Locked decision 11 — reconciles an earlier inconsistent revision)', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('/emulators/profiles/some-slug is not a registered route — falls through to the section default tab', async () => {
    mockApiGenerically()
    renderAt('/emulators/profiles/some-slug')
    // No `/emulators/profiles/:slug` route exists, so this hits the nested
    // catch-all under `/emulators` (built by buildTabRoutes) and redirects to
    // the section's default tab — it does NOT 404 and does NOT render Profiles
    // with a specific profile selected (there is no such concept).
    await expectFinalPath('/emulators/emulators')
  })
})
