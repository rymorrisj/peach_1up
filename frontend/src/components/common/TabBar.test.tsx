import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as Tabs from '@radix-ui/react-tabs'
import TabBar from '@/components/common/TabBar'

const TABS = [
  { id: 'overview' as const, label: 'Overview' },
  { id: 'settings' as const, label: 'Settings' },
  { id: 'history' as const, label: 'History' },
]

function renderTabBar(defaultValue = 'overview') {
  return render(
    <Tabs.Root defaultValue={defaultValue}>
      <TabBar tabs={TABS} />
    </Tabs.Root>,
  )
}

describe('TabBar', () => {
  it('renders a tab trigger for every tab', () => {
    renderTabBar()
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'History' })).toBeInTheDocument()
  })

  it('marks the default tab as selected', () => {
    renderTabBar()
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveAttribute('aria-selected', 'false')
  })

  it('selects a tab when clicked', async () => {
    const user = userEvent.setup()
    renderTabBar()
    await user.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(screen.getByRole('tab', { name: 'Settings' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'false')
  })

  it('renders with a single tab without crashing', () => {
    render(
      <Tabs.Root defaultValue="only">
        <TabBar tabs={[{ id: 'only', label: 'Only Tab' }]} />
      </Tabs.Root>,
    )
    expect(screen.getByRole('tab', { name: 'Only Tab' })).toBeInTheDocument()
  })
})
