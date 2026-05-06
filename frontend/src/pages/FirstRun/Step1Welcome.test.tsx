import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/helpers'
import Step1Welcome from './Step1Welcome'

describe('Step1Welcome', () => {
  it('renders heading', () => {
    renderWithProviders(<Step1Welcome onNext={vi.fn()} />)
    expect(
      screen.getByRole('heading', { name: /welcome to peach 1up/i }),
    ).toBeInTheDocument()
  })

  it('renders CTA button', () => {
    renderWithProviders(<Step1Welcome onNext={vi.fn()} />)
    expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument()
  })

  it('calls onNext when CTA clicked', async () => {
    const user = userEvent.setup()
    const onNext = vi.fn()
    renderWithProviders(<Step1Welcome onNext={onNext} />)
    await user.click(screen.getByRole('button', { name: /get started/i }))
    expect(onNext).toHaveBeenCalledTimes(1)
  })
})
