import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TabBar from '@/components/common/TabBar'

const TABS = [
  { id: 'overview' as const, label: 'Overview' },
  { id: 'settings' as const, label: 'Settings' },
  { id: 'history' as const, label: 'History' },
]

describe('TabBar', () => {
  it('renders a button for every tab', () => {
    render(<TabBar tabs={TABS} activeTab="overview" onTabChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'History' })).toBeInTheDocument()
  })

  it('calls onTabChange with the tab id when an inactive tab is clicked', async () => {
    const user = userEvent.setup()
    const onTabChange = vi.fn()
    render(<TabBar tabs={TABS} activeTab="overview" onTabChange={onTabChange} />)
    await user.click(screen.getByRole('button', { name: 'Settings' }))
    expect(onTabChange).toHaveBeenCalledWith('settings')
  })

  it('calls onTabChange even when the active tab is clicked', async () => {
    const user = userEvent.setup()
    const onTabChange = vi.fn()
    render(<TabBar tabs={TABS} activeTab="overview" onTabChange={onTabChange} />)
    await user.click(screen.getByRole('button', { name: 'Overview' }))
    expect(onTabChange).toHaveBeenCalledWith('overview')
  })

  it('renders with a single tab without crashing', () => {
    render(<TabBar tabs={[{ id: 'only', label: 'Only Tab' }]} activeTab="only" onTabChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Only Tab' })).toBeInTheDocument()
  })
})
