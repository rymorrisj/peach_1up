import { render, screen, within } from '@testing-library/react';
import { FilesSection, type FileListEntry } from './FilesSection';

function entry(overrides: Partial<FileListEntry> & { id: number }): FileListEntry {
  return {
    title: `File ${overrides.id}`,
    file_path: `C:\\library\\media\\file-${overrides.id}.png`,
    file_url: `/media/media/file-${overrides.id}.png`,
    file_size_bytes: null,
    media_kind: 'image',
    asset_type: null,
    ...overrides,
  };
}

function groupHeadings(): string[] {
  return screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent ?? '');
}

describe('FilesSection', () => {
  it('renders nothing for an empty list', () => {
    const { container } = render(<FilesSection items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('groups by asset type first, then media kind, with unknown kinds under Other', () => {
    render(
      <FilesSection
        items={[
          entry({ id: 1, media_kind: 'weird' }),
          entry({ id: 2, media_kind: 'audio', file_url: null }),
          entry({ id: 3, asset_type: 'screenshot' }),
          entry({ id: 4, asset_type: 'boxart_front' }),
          entry({ id: 5 }),
        ]}
      />,
    );

    expect(groupHeadings()).toEqual([
      'Box art (front) (1)',
      'Screenshots (1)',
      'Images (1)',
      'Audio (1)',
      'Other (1)',
    ]);
  });

  it('shows each file by title, not by file name', () => {
    render(<FilesSection items={[entry({ id: 1, title: 'Front of the box' })]} />);

    expect(screen.getByText('Front of the box')).toBeInTheDocument();
    expect(screen.queryByText('file-1.png')).not.toBeInTheDocument();
  });

  it('renders an image file as a thumbnail linking to its URL', () => {
    render(<FilesSection items={[entry({ id: 1, title: 'Shot' })]} />);

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/media/media/file-1.png');
    expect(within(link).getByRole('img', { name: 'Shot' })).toBeInTheDocument();
  });

  it('marks the current cover when the stored path differs only in slashes and case', () => {
    render(
      <FilesSection
        items={[entry({ id: 1 }), entry({ id: 2 })]}
        currentCoverArtPath="c:/Library//MEDIA/file-1.png"
        onSetCoverArt={() => {}}
      />,
    );

    expect(screen.getByText('Cover art')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Set as cover art' })).toHaveLength(1);
  });

  it('offers Set as cover art on every image when no cover matches', () => {
    render(
      <FilesSection
        items={[entry({ id: 1 }), entry({ id: 2 })]}
        currentCoverArtPath={null}
        onSetCoverArt={() => {}}
      />,
    );

    expect(screen.queryByText('Cover art')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Set as cover art' })).toHaveLength(2);
  });
});
