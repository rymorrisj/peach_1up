import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/helpers'
import Step4Profile from './Step4Profile'
import * as client from '@/api/client'

describe('Step4Profile', () => {
  it('renders the Finish Setup button', () => {
    renderWithProviders(<Step4Profile onComplete={vi.fn()} />)
    expect(screen.getByRole('button', { name: /finish setup/i })).toBeInTheDocument()
  })

  it('calls complete-first-run and invokes onComplete', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    vi.spyOn(client, 'apiFetch').mockResolvedValue({ success: true } as never)

    renderWithProviders(<Step4Profile onComplete={onComplete} />)
    await user.click(screen.getByRole('button', { name: /finish setup/i }))

    await waitFor(() => {
      expect(client.apiFetch).toHaveBeenCalledWith(
        '/api/v1/settings/complete-first-run',
        expect.objectContaining({ method: 'POST' }),
      )
      expect(onComplete).toHaveBeenCalled()
    })
  })

  it('shows inline error when complete-first-run fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(client, 'apiFetch').mockRejectedValue(
      Object.assign(new Error(), { detail: 'Setup failed.' }),
    )

    renderWithProviders(<Step4Profile onComplete={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /finish setup/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })
})
