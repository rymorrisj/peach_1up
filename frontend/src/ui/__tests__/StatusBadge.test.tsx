import { render, screen } from '@testing-library/react'
import { StatusBadge } from '@/ui/StatusBadge'

describe('StatusBadge', () => {
  it('renders "OK" for status="ok" with no custom label', () => {
    render(<StatusBadge status="ok" />)
    expect(screen.getByText('OK')).toBeInTheDocument()
  })

  it('renders "Missing" for status="missing"', () => {
    render(<StatusBadge status="missing" />)
    expect(screen.getByText('Missing')).toBeInTheDocument()
  })

  it('renders "Error" for status="error"', () => {
    render(<StatusBadge status="error" />)
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('renders "Unknown" for an unrecognised status value', () => {
    render(<StatusBadge status="not-a-real-status" />)
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })

  it('renders the custom label when label prop is provided, regardless of status', () => {
    render(<StatusBadge status="ok" label="All systems go" />)
    expect(screen.getByText('All systems go')).toBeInTheDocument()
  })
})
