import { render, screen } from '@testing-library/react'
import { PageHeader } from '@/ui/PageHeader'

describe('PageHeader', () => {
  it('renders the title as a heading', () => {
    render(<PageHeader title="Library" />)
    expect(screen.getByRole('heading', { name: 'Library' })).toBeInTheDocument()
  })

  it('renders a count next to the title when count is provided', () => {
    render(<PageHeader title="Library" count={42} />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('does not render the count span when count is undefined', () => {
    render(<PageHeader title="Library" />)
    // heading is the only text node; no extra count span
    expect(screen.queryByText(/\d+/)).not.toBeInTheDocument()
  })

  it('renders description text when provided', () => {
    render(<PageHeader title="Settings" description="Configure your setup" />)
    expect(screen.getByText('Configure your setup')).toBeInTheDocument()
  })

  it('renders action slot content when provided', () => {
    render(<PageHeader title="Tags" action={<button>Add Tag</button>} />)
    expect(screen.getByRole('button', { name: 'Add Tag' })).toBeInTheDocument()
  })

  it('does not render action slot when action is not provided', () => {
    render(<PageHeader title="Library" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
