import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Toast } from '@/ui/Toast'

describe('Toast', () => {
  it('renders the message', () => {
    render(<Toast message="Saved successfully" onDismiss={vi.fn()} />)
    expect(screen.getByText('Saved successfully')).toBeInTheDocument()
  })

  it('calls onDismiss when the dismiss button is clicked', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<Toast message="Something failed" onDismiss={onDismiss} />)
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('calls onDismiss when the toast body is clicked', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<Toast message="Click to dismiss" onDismiss={onDismiss} />)
    await user.click(screen.getByRole('alert'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('auto-dismisses after the given duration', () => {
    vi.useFakeTimers()
    const onDismiss = vi.fn()
    render(<Toast message="Auto dismiss" duration={1000} onDismiss={onDismiss} />)
    expect(onDismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(onDismiss).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('does not auto-dismiss when duration is 0', () => {
    vi.useFakeTimers()
    const onDismiss = vi.fn()
    render(<Toast message="Sticky" duration={0} onDismiss={onDismiss} />)
    vi.advanceTimersByTime(10_000)
    expect(onDismiss).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('renders each variant without crashing', () => {
    const variants = ['success', 'error', 'info'] as const
    for (const variant of variants) {
      const { unmount } = render(<Toast message="Label" variant={variant} onDismiss={vi.fn()} />)
      expect(screen.getByRole('alert')).toBeInTheDocument()
      unmount()
    }
  })
})
