import { render, screen } from '@testing-library/react'
import EmulatorStatus from '@/components/emulators/EmulatorStatus'

describe('EmulatorStatus', () => {
  it('displays "Healthy" for status "ok"', () => {
    render(<EmulatorStatus status="ok" />)
    expect(screen.getByText('Healthy')).toBeInTheDocument()
  })

  it('displays "Healthy" for status "healthy"', () => {
    render(<EmulatorStatus status="healthy" />)
    expect(screen.getByText('Healthy')).toBeInTheDocument()
  })

  it('displays "Missing" for status "missing"', () => {
    render(<EmulatorStatus status="missing" />)
    expect(screen.getByText('Missing')).toBeInTheDocument()
  })

  it('displays "Error" for status "error"', () => {
    render(<EmulatorStatus status="error" />)
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('displays "Unconfigured" for status "unconfigured"', () => {
    render(<EmulatorStatus status="unconfigured" />)
    expect(screen.getByText('Unconfigured')).toBeInTheDocument()
  })

  it('falls back to the raw status string for an unrecognised value', () => {
    render(<EmulatorStatus status="pending-install" />)
    expect(screen.getByText('pending-install')).toBeInTheDocument()
  })
})
