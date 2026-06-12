import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LaunchCommandList from '@/components/LaunchCommandList'

describe('LaunchCommandList', () => {
  it('renders the "Add command" button when the list is empty', () => {
    render(<LaunchCommandList value={[]} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /add command/i })).toBeInTheDocument()
  })

  it('shows "—" in the combined preview when there are no commands', () => {
    render(<LaunchCommandList value={[]} onChange={vi.fn()} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders one input per command', () => {
    render(<LaunchCommandList value={['C:\\game.exe', 'D:\\mod.exe']} onChange={vi.fn()} />)
    expect(screen.getAllByRole('textbox')).toHaveLength(2)
  })

  it('calls onChange with an appended empty string when Add is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<LaunchCommandList value={['C:\\game.exe']} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /add command/i }))
    expect(onChange).toHaveBeenCalledWith(['C:\\game.exe', ''])
  })

  it('calls onChange without the removed entry when the remove button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<LaunchCommandList value={['C:\\game.exe']} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /remove command/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('shows commands joined with " && " in the combined-command preview', () => {
    render(<LaunchCommandList value={['C:\\a.exe', 'C:\\b.exe']} onChange={vi.fn()} />)
    expect(screen.getByText('C:\\a.exe && C:\\b.exe')).toBeInTheDocument()
  })

  it('disables all buttons when disabled prop is set', () => {
    render(<LaunchCommandList value={['C:\\game.exe']} onChange={vi.fn()} disabled />)
    for (const btn of screen.getAllByRole('button')) {
      expect(btn).toBeDisabled()
    }
  })
})
