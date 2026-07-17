import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Modal } from '@/ui/Modal'

describe('Modal', () => {
  it('renders the title and children when open', () => {
    render(
      <Modal open title="Confirm Action" onClose={vi.fn()}>
        Modal body content
      </Modal>,
    )
    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
    expect(screen.getByText('Modal body content')).toBeInTheDocument()
  })

  it('renders the dialog when open is true', () => {
    render(<Modal open title="Test" onClose={vi.fn()}>Content</Modal>)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders nothing when open is false', () => {
    render(<Modal open={false} title="Test" onClose={vi.fn()}>Content</Modal>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders footer content when the footer prop is provided', () => {
    render(
      <Modal open title="Dialog" onClose={vi.fn()} footer={<button>OK</button>}>
        Body
      </Modal>,
    )
    expect(screen.getByRole('button', { name: 'OK' })).toBeInTheDocument()
  })

  it('does not render any footer buttons when footer is not provided', () => {
    render(<Modal open title="Dialog" onClose={vi.fn()}>Body</Modal>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('fires onClose when a footer button triggers it', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <Modal open title="Dialog" onClose={onClose} footer={<button onClick={onClose}>Close</button>}>
        Body
      </Modal>,
    )
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
