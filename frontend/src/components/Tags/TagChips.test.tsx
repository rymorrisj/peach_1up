import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TagChips from '@/components/Tags/TagChips';
import type { components } from '@shared/types';

type TagRead = components['schemas']['TagRead'];

const SAMPLE_TAGS: TagRead[] = [
  { id: 1, name: 'action', color: 'coral', item_count: 5, is_system: false },
  { id: 2, name: 'retro', color: 'amber', item_count: 3, is_system: false },
];

describe('TagChips', () => {
  it('renders a placeholder message when the tag list is empty', () => {
    render(<TagChips tags={[]} />);
    expect(screen.getByText('No tags.')).toBeInTheDocument();
  });

  it('renders a chip for each tag', () => {
    render(<TagChips tags={SAMPLE_TAGS} />);
    expect(screen.getByText('action')).toBeInTheDocument();
    expect(screen.getByText('retro')).toBeInTheDocument();
  });

  it('does not render remove buttons when onRemove is not provided', () => {
    render(<TagChips tags={SAMPLE_TAGS} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders a remove button for each tag when onRemove is provided', () => {
    render(<TagChips tags={SAMPLE_TAGS} onRemove={vi.fn()} />);
    expect(screen.getAllByRole('button')).toHaveLength(2);
  });

  it('calls onRemove with the tag id when the remove button is clicked', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<TagChips tags={SAMPLE_TAGS} onRemove={onRemove} />);
    await user.click(screen.getByRole('button', { name: 'Remove tag action' }));
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('does not render a remove button for a system tag even when onRemove is provided', () => {
    const tags: TagRead[] = [
      { id: 1, name: 'action', color: 'coral', item_count: 5, is_system: false },
      { id: 2, name: 'MT-32', color: 'amber', item_count: 0, is_system: true },
    ];
    render(<TagChips tags={tags} onRemove={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Remove tag action' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove tag MT-32' })).not.toBeInTheDocument();
  });
});
