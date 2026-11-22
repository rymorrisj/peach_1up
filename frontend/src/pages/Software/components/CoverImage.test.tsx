import { fireEvent, render, screen } from '@testing-library/react';
import { CoverImage } from './CoverImage';

const fallback = <div data-testid="placeholder">Placeholder</div>;

describe('CoverImage', () => {
  it('renders the image when the url is set and has not failed', () => {
    render(<CoverImage src="/media/a.jpg" alt="Ico" fallback={fallback} />);

    expect(screen.getByRole('img', { name: 'Ico' })).toHaveAttribute('src', '/media/a.jpg');
    expect(screen.queryByTestId('placeholder')).not.toBeInTheDocument();
  });

  it('shows the placeholder when the image fails to load', () => {
    render(<CoverImage src="/media/broken.jpg" alt="Ico" fallback={fallback} />);

    fireEvent.error(screen.getByRole('img', { name: 'Ico' }));

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByTestId('placeholder')).toBeInTheDocument();
  });

  it('tries the new image again when the url changes after a failure', () => {
    const { rerender } = render(
      <CoverImage src="/media/broken.jpg" alt="Ico" fallback={fallback} />,
    );
    fireEvent.error(screen.getByRole('img', { name: 'Ico' }));
    expect(screen.getByTestId('placeholder')).toBeInTheDocument();

    rerender(<CoverImage src="/media/fixed.jpg" alt="Ico" fallback={fallback} />);

    expect(screen.getByRole('img', { name: 'Ico' })).toHaveAttribute('src', '/media/fixed.jpg');
    expect(screen.queryByTestId('placeholder')).not.toBeInTheDocument();
  });

  it('keeps the placeholder when the failed url comes back unchanged', () => {
    const { rerender } = render(
      <CoverImage src="/media/broken.jpg" alt="Ico" fallback={fallback} />,
    );
    fireEvent.error(screen.getByRole('img', { name: 'Ico' }));

    rerender(<CoverImage src="/media/broken.jpg" alt="Ico" fallback={fallback} />);

    expect(screen.getByTestId('placeholder')).toBeInTheDocument();
  });

  it.each([null, undefined, ''])('shows the placeholder for a falsy url (%s)', (src) => {
    render(<CoverImage src={src} alt="Ico" fallback={fallback} />);

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByTestId('placeholder')).toBeInTheDocument();
  });
});
