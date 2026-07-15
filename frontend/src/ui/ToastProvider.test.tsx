import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider, useToast } from '@/ui/ToastProvider'

function Trigger() {
  const { showToast } = useToast()
  return (
    <>
      <button onClick={() => showToast('First toast')}>Show info</button>
      <button onClick={() => showToast('Something broke', 'error')}>Show error</button>
    </>
  )
}

describe('ToastProvider / useToast', () => {
  it('throws when useToast is called outside a ToastProvider', () => {
    const Bare = () => {
      useToast()
      return null
    }
    // Suppress the expected React error boundary console noise for this assertion.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Bare />)).toThrow('useToast must be used within ToastProvider')
    spy.mockRestore()
  })

  it('renders a toast pushed via showToast', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Show info' }))
    expect(screen.getByText('First toast')).toBeInTheDocument()
  })

  it('stacks multiple toasts', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Show info' }))
    await user.click(screen.getByRole('button', { name: 'Show error' }))
    expect(screen.getAllByRole('alert')).toHaveLength(2)
  })

  it('removes a toast from the queue when dismissed', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Show info' }))
    expect(screen.getByText('First toast')).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Dismiss' })[0])
    expect(screen.queryByText('First toast')).not.toBeInTheDocument()
  })
})
