import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/helpers';
import ConfirmModal from './ConfirmModal';

describe('ConfirmModal', () => {
  it('renders title and consequence when open', () => {
    renderWithProviders(
      <ConfirmModal
        open
        title="Delete item?"
        consequence="This action cannot be undone."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete item?')).toBeInTheDocument();
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument();
  });

  it('calls onCancel when cancel is clicked', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderWithProviders(
      <ConfirmModal
        open
        title="Delete?"
        consequence="Permanent."
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onConfirm when confirm is clicked', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderWithProviders(
      <ConfirmModal
        open
        title="Delete?"
        consequence="Permanent."
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('cancel button has autofocus', () => {
    renderWithProviders(
      <ConfirmModal
        open
        title="Delete?"
        consequence="Permanent."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    // React calls .focus() for autoFocus on commit — verify the element actually receives focus
    expect(cancelBtn).toHaveFocus();
  });
});
