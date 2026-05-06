import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/helpers'
import Step4Profile from './Step4Profile'
import * as client from '@/api/client'

describe('Step4Profile', () => {
  it('submit button is disabled when name is empty', () => {
    renderWithProviders(<Step4Profile onComplete={vi.fn()} />)
    expect(screen.getByRole('button', { name: /finish setup/i })).toBeDisabled()
  })

  it('calls owner API with name and null PIN when PIN not provided', async () => {
    const user = userEvent.setup()
    vi.spyOn(client, 'apiFetch').mockResolvedValue({ success: true } as never)

    renderWithProviders(<Step4Profile onComplete={vi.fn()} />)

    await user.type(screen.getByLabelText(/display name/i), 'Ryan')
    await user.click(screen.getByRole('button', { name: /finish setup/i }))

    await waitFor(() => {
      expect(client.apiFetch).toHaveBeenCalledWith(
        '/api/v1/profiles/users/owner',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'Ryan', pin: null }),
        }),
      )
    })
  })

  it('shows inline error when name is missing on submit', () => {
    renderWithProviders(<Step4Profile onComplete={vi.fn()} />)
    const form = document.querySelector('form')!
    fireEvent.submit(form)
    expect(screen.getByRole('alert')).toHaveTextContent(/display name is required/i)
  })
})
