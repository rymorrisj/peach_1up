import { render, screen } from '@testing-library/react';
import { MediaEditForm, type MediaRatingInheritance } from './MediaEditForm';
import type { SoftwareMediaForm } from '../types/mediaForm';

const form: SoftwareMediaForm = {
  title: 'Doom OST',
  description: '',
  content_rating: 'T',
};

function renderForm(rating: MediaRatingInheritance) {
  return render(
    <MediaEditForm
      form={form}
      setField={() => {}}
      rating={rating}
      handleSave={() => {}}
      saving={false}
      saveError={null}
      saveSuccess={false}
    />,
  );
}

describe('MediaEditForm cover art', () => {
  it('has no path input or browse button, so media-only editors never hit browse', () => {
    renderForm({ isInherited: false, effectiveRating: null });

    expect(screen.queryByLabelText('Cover Art Path')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Browse…' })).not.toBeInTheDocument();
  });
});

describe('MediaEditForm content rating', () => {
  it('shows an editable rating field for a standalone bundle', () => {
    renderForm({ isInherited: false, effectiveRating: 'T' });

    expect(screen.getByLabelText('Content Rating')).toBeInTheDocument();
    expect(screen.queryByText(/Inherited from linked software/)).not.toBeInTheDocument();
  });

  it('shows read-only inherited text and no field for a linked bundle', () => {
    renderForm({ isInherited: true, effectiveRating: 'M' });

    expect(screen.getByText('Inherited from linked software: M')).toBeInTheDocument();
    expect(screen.queryByLabelText('Content Rating')).not.toBeInTheDocument();
  });

  it('shows Unrated when every linked game is unrated', () => {
    renderForm({ isInherited: true, effectiveRating: null });

    expect(screen.getByText('Inherited from linked software: Unrated')).toBeInTheDocument();
  });
});
