import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BiosPlaceAction } from './BiosPlaceAction'
import type { components } from '@shared/types'
type BiosRequirement = components['schemas']['BiosRequirement']

// FileBrowser drives its own dialog/query plumbing — out of scope here. Stubbed
// to a single button that immediately fires onSelect with a fixed path, so
// these tests exercise BiosPlaceAction's own fetch/state logic in isolation.
vi.mock('@/components/common/FileBrowser', () => ({
  default: ({ open, onSelect }: { open: boolean; onSelect: (path: string) => void }) =>
    open ? <button onClick={() => onSelect('/fake/path/to/bios')}>fake-select</button> : null,
}))

function renderAction(bios: BiosRequirement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <BiosPlaceAction bios={bios} />
    </QueryClientProvider>,
  )
}

const PS1_BIOS: BiosRequirement = {
  slug: 'ps1-bios',
  name: 'PS1 BIOS',
  platform: 'ps1',
  bios_path: 'emulators/duckstation/bios',
  guidance_text: 'Place your PS1 BIOS file.',
  guidance_url: 'https://example.invalid',
  is_present: false,
  required: true,
}

describe('BiosPlaceAction', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('renders nothing for a slug without a placement mode (xbox-bios reuses its own flow)', () => {
    renderAction({ ...PS1_BIOS, slug: 'xbox-bios' })
    expect(screen.queryByText(/Locate file\/folder/)).not.toBeInTheDocument()
  })

  it('renders the Locate action for a supported slug', () => {
    renderAction(PS1_BIOS)
    expect(screen.getByText(/Locate file\/folder/)).toBeInTheDocument()
  })

  it('posts source_path as FormData to the place endpoint and shows success', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        slug: 'ps1-bios', is_present: true, copied: ['scph1001.bin'], skipped: [], warnings: [],
      }),
    })

    renderAction(PS1_BIOS)
    fireEvent.click(screen.getByText(/Locate file\/folder/))
    fireEvent.click(screen.getByText('fake-select'))

    await waitFor(() => expect(screen.getByText(/Placed 1 file/)).toBeInTheDocument())

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/api/v1/bios/ps1-bios/place')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('source_path')).toBe('/fake/path/to/bios')
  })

  it('surfaces the backend rejection message on a non-2xx response', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'No PS1 BIOS (.bin) files found.' }),
    })

    renderAction(PS1_BIOS)
    fireEvent.click(screen.getByText(/Locate file\/folder/))
    fireEvent.click(screen.getByText('fake-select'))

    await waitFor(() => expect(screen.getByText(/No PS1 BIOS \(\.bin\) files found/)).toBeInTheDocument())
  })

  it('surfaces warnings from a successful but imperfect placement', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        slug: 'mesen-fds-bios', is_present: true, copied: ['FdsBios.bin'], skipped: [],
        warnings: ['SHA1 does not match the known-good FDS BIOS hash.'],
      }),
    })

    renderAction({ ...PS1_BIOS, slug: 'mesen-fds-bios', name: 'Mesen FDS BIOS', required: false })
    fireEvent.click(screen.getByText(/Locate file\/folder/))
    fireEvent.click(screen.getByText('fake-select'))

    await waitFor(() =>
      expect(screen.getByText(/does not match the known-good FDS BIOS hash/)).toBeInTheDocument(),
    )
  })
})
