import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Tooltip } from '@/ui/Tooltip'

describe('Tooltip', () => {
  it('renders the trigger', () => {
    render(
      <Tooltip content="Helpful hint">
        <button>Hover me</button>
      </Tooltip>,
    )
    expect(screen.getByRole('button', { name: 'Hover me' })).toBeInTheDocument()
  })

  it('shows the content on hover', async () => {
    const user = userEvent.setup()
    render(
      <Tooltip content="Helpful hint">
        <button>Hover me</button>
      </Tooltip>,
    )
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    await user.hover(screen.getByRole('button', { name: 'Hover me' }))
    await waitFor(() => {
      expect(screen.getByRole('tooltip')).toHaveTextContent('Helpful hint')
    })
  })

  it('shows the content on focus', async () => {
    const user = userEvent.setup()
    render(
      <Tooltip content="Helpful hint">
        <button>Hover me</button>
      </Tooltip>,
    )
    await user.tab()
    await waitFor(() => {
      expect(screen.getByRole('tooltip')).toHaveTextContent('Helpful hint')
    })
  })
})
