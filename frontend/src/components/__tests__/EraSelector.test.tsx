import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EraSelector from '@/components/common/EraSelector'

describe('EraSelector', () => {
  it('renders PC and Console group headings', () => {
    render(<EraSelector value={null} onChange={vi.fn()} />)
    expect(screen.getByText('PC')).toBeInTheDocument()
    expect(screen.getByText('Console')).toBeInTheDocument()
  })

  it('renders individual era buttons', () => {
    render(<EraSelector value={null} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'DOS' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'PlayStation 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nintendo 64' })).toBeInTheDocument()
  })

  it('marks the currently selected era button as pressed', () => {
    render(<EraSelector value="dos" onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'DOS' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('marks all other era buttons as not pressed', () => {
    render(<EraSelector value="dos" onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Windows 98' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('calls onChange with the era value when a button is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<EraSelector value={null} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: 'Windows 98' }))
    expect(onChange).toHaveBeenCalledWith('win98')
  })

  it('disables all era buttons when the disabled prop is set', () => {
    render(<EraSelector value={null} onChange={vi.fn()} disabled />)
    for (const btn of screen.getAllByRole('button')) {
      expect(btn).toBeDisabled()
    }
  })
})
