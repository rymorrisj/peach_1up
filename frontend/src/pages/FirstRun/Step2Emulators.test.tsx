import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/helpers'
import Step2Emulators from './Step2Emulators'
import type { FirstRunStatus, CatalogEntry } from './types'
import * as client from '@/api/client'

const mockStatus: FirstRunStatus = {
  first_run_complete: false,
  owner_profile_exists: false,
  emulators: [
    { slug: 'dosbox-x', name: 'DOSBox-X', required: true, available: false, path: null },
    { slug: '86box', name: '86Box', required: false, available: false, path: null },
  ],
  owner_exists: false,
  paths: { library_path: null, profiles_path: null, rom_path: null },
}

const mockCatalog: CatalogEntry[] = [
  {
    slug: 'dosbox-x',
    name: 'DOSBox-X',
    version: 'PLACEHOLDER',
    description: 'DOS emulation',
    license: 'GPL-2.0',
    required: true,
    is_installed: false,
    install_path: null,
    install_type: 'zip',
    install_scope: 'portable',
    installer_present: false,
    git_available: null,
    is_placeholder: false,
  },
  {
    slug: '86box',
    name: '86Box',
    version: 'PLACEHOLDER',
    description: 'Win 95/98 accuracy',
    license: 'GPL-2.0',
    required: false,
    is_installed: false,
    install_path: null,
    install_type: 'zip',
    install_scope: 'portable',
    installer_present: false,
    git_available: null,
    is_placeholder: true,
  },
]

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Step2Emulators', () => {
  it('renders emulator rows from mock status data', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((path) => {
      if (path === '/api/v1/emulators') return Promise.resolve(mockCatalog)
      return Promise.reject(new client.ApiError(404, 'not found'))
    })

    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)
    expect(await screen.findByText('DOSBox-X')).toBeInTheDocument()
    expect(await screen.findByText('86Box')).toBeInTheDocument()
  })

  it('install button renders for non-placeholder emulators', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((path) => {
      if (path === '/api/v1/emulators') return Promise.resolve(mockCatalog)
      return Promise.reject(new client.ApiError(404, 'not found'))
    })

    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)
    await waitFor(() => {
      const dosboxRow = screen.getByText('DOSBox-X').closest('li')!
      expect(within(dosboxRow).getByRole('button', { name: /install dosbox-x/i })).toBeInTheDocument()
    })
  })

  it('"Not yet available" badge renders for placeholder emulators', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((path) => {
      if (path === '/api/v1/emulators') return Promise.resolve(mockCatalog)
      return Promise.reject(new client.ApiError(404, 'not found'))
    })

    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('Not yet available')).toBeInTheDocument()
    })
  })

  it('polling starts after install button clicked', async () => {
    const user = userEvent.setup()
    vi.spyOn(client, 'apiFetch').mockImplementation((path) => {
      if (path === '/api/v1/emulators') return Promise.resolve(mockCatalog)
      if (path === '/api/v1/emulators/dosbox-x/install')
        return Promise.resolve({ status: 'downloading', slug: 'dosbox-x' })
      if (path === '/api/v1/emulators/dosbox-x/install/status')
        return Promise.resolve({ slug: 'dosbox-x', status: 'downloading', error: null, install_path: null })
      return Promise.reject(new client.ApiError(404, 'not found'))
    })

    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)

    const installBtn = await screen.findByRole('button', { name: /install dosbox-x/i })
    await user.click(installBtn)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /installing dosbox-x/i })).toBeInTheDocument()
    })
  })

  it('save button calls API with correct slug and path', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((path) => {
      if (path === '/api/v1/emulators') return Promise.resolve(mockCatalog)
      if (path === '/api/v1/settings/emulator-path')
        return Promise.resolve({ slug: 'dosbox-x', path: '/usr/bin/dosbox', available: true })
      return Promise.reject(new client.ApiError(404, 'not found'))
    })

    const user = userEvent.setup()
    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)

    const dosboxRow = (await screen.findByText('DOSBox-X')).closest('li')!
    const input = within(dosboxRow).getByLabelText(/dosbox-x binary path/i)
    await user.type(input, '/usr/bin/dosbox')

    const saveBtn = within(dosboxRow).getByRole('button', { name: /save/i })
    await user.click(saveBtn)

    await waitFor(() => {
      expect(client.apiFetch).toHaveBeenCalledWith(
        '/api/v1/settings/emulator-path',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ slug: 'dosbox-x', path: '/usr/bin/dosbox' }),
        }),
      )
    })
  })

  it('shows inline error when API returns 400', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((path) => {
      if (path === '/api/v1/emulators') return Promise.resolve(mockCatalog)
      if (path === '/api/v1/settings/emulator-path')
        return Promise.reject(new client.ApiError(400, 'Path does not exist.'))
      return Promise.reject(new client.ApiError(404, 'not found'))
    })

    const user = userEvent.setup()
    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)

    const dosboxRow = (await screen.findByText('DOSBox-X')).closest('li')!
    const input = within(dosboxRow).getByLabelText(/dosbox-x binary path/i)
    await user.type(input, '/bad/path')

    const saveBtn = within(dosboxRow).getByRole('button', { name: /save/i })
    await user.click(saveBtn)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Path does not exist.')
    })
  })
})
