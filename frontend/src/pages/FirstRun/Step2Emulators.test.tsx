import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/helpers'
import Step2Emulators from './Step2Emulators'
import type { FirstRunStatus } from './types'
import * as client from '@/api/client'

const mockStatus: FirstRunStatus = {
  first_run_complete: false,
  owner_profile_exists: false,
  emulators: [
    { slug: 'dosbox-x', name: 'DOSBox-X', required: true, available: false, path: null },
    { slug: '86box', name: '86Box', required: false, available: false, path: null },
  ],
  paths: { images_path: null, profiles_path: null, rom_path: null },
}

describe('Step2Emulators', () => {
  it('renders emulator rows from mock status data', () => {
    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)
    expect(screen.getByText('DOSBox-X')).toBeInTheDocument()
    expect(screen.getByText('86Box')).toBeInTheDocument()
  })

  it('save button calls API with correct slug and path', async () => {
    const user = userEvent.setup()
    vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({
      slug: 'dosbox-x',
      path: '/usr/bin/dosbox',
      available: true,
    })

    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)

    const dosboxRow = screen.getByText('DOSBox-X').closest('li')!
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
    const user = userEvent.setup()
    vi.spyOn(client, 'apiFetch').mockRejectedValueOnce(
      new client.ApiError(400, 'Path does not exist.'),
    )

    renderWithProviders(<Step2Emulators status={mockStatus} onNext={vi.fn()} />)

    const dosboxRow = screen.getByText('DOSBox-X').closest('li')!
    const input = within(dosboxRow).getByLabelText(/dosbox-x binary path/i)
    await user.type(input, '/bad/path')

    const saveBtn = within(dosboxRow).getByRole('button', { name: /save/i })
    await user.click(saveBtn)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Path does not exist.')
    })
  })
})
