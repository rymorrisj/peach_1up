import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/helpers';
import EmptyState from './EmptyState';

describe('EmptyState', () => {
  it('renders heading and subtext', () => {
    renderWithProviders(
      <EmptyState heading="Nothing here yet" subtext="Add something to get started." />,
    );

    expect(screen.getByRole('heading', { name: 'Nothing here yet' })).toBeInTheDocument();
    expect(screen.getByText('Add something to get started.')).toBeInTheDocument();
  });

  it('renders CTA button when cta prop is provided', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWithProviders(<EmptyState heading="Empty" cta={{ label: 'Add Item', onClick }} />);

    const btn = screen.getByRole('button', { name: 'Add Item' });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not render CTA when cta prop is absent', () => {
    renderWithProviders(<EmptyState heading="Empty" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
