import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/helpers'
import ErrorModal from './ErrorModal'

describe('ErrorModal', () => {
  it('renders title, cause, and one option when open', () => {
    const handler = vi.fn()
    renderWithProviders(
      <ErrorModal
        open
        title="Something went wrong"
        cause="The backend returned a 500 error."
        options={[{ label: 'Dismiss', handler }]}
      />,
    )

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('The backend returned a 500 error.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeInTheDocument()
  })

  it('calls option handler when option button is clicked', async () => {
    const user = userEvent.setup()
    const handler = vi.fn()
    renderWithProviders(
      <ErrorModal
        open
        title="Error"
        cause="Something failed."
        options={[{ label: 'Retry', handler }]}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('does not show dialog content when closed', () => {
    renderWithProviders(
      <ErrorModal
        open={false}
        title="Hidden"
        cause="Not visible."
        options={[]}
      />,
    )

    // Dialog is in the DOM but has no `open` attribute when closed
    const dialog = document.querySelector('dialog')
    expect(dialog).not.toHaveAttribute('open')
  })
})
