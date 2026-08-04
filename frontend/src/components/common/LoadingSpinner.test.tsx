import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/helpers';
import LoadingSpinner from './LoadingSpinner';

describe('LoadingSpinner', () => {
  it('renders with role="status"', () => {
    renderWithProviders(<LoadingSpinner />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders label as visually hidden text when provided', () => {
    renderWithProviders(<LoadingSpinner label="Loading library…" />);
    const hidden = screen.getByText('Loading library…');
    expect(hidden).toHaveClass('sr-only');
  });
});
