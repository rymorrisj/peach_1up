import { render, screen } from '@testing-library/react';
import { ExternalLinksSection } from './ExternalLinksSection';
import { isWebUrl } from './externalLinks';

describe('ExternalLinksSection', () => {
  it('lists links grouped by type as new-tab anchors', () => {
    render(
      <ExternalLinksSection
        links={[
          { type: 'trailer', url: 'https://youtu.be/abc', source: 'provider' },
          { type: 'official', url: 'https://doom.example/', source: 'provider' },
          { type: 'store', url: 'http://store.example/doom' },
        ]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Links' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Trailers' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Official sites' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Stores' })).toBeInTheDocument();

    const trailer = screen.getByRole('link', { name: 'https://youtu.be/abc' });
    expect(trailer).toHaveAttribute('href', 'https://youtu.be/abc');
    expect(trailer).toHaveAttribute('target', '_blank');
    expect(trailer).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('link', { name: 'http://store.example/doom' })).toBeInTheDocument();
  });

  it('shows the trailer group before the site groups', () => {
    render(
      <ExternalLinksSection
        links={[
          { type: 'official', url: 'https://doom.example/' },
          { type: 'trailer', url: 'https://youtu.be/abc' },
        ]}
      />,
    );
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(['Trailers', 'Official sites']);
  });

  it('renders nothing when the links are omitted, empty or null', () => {
    const { container, rerender } = render(<ExternalLinksSection links={undefined} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ExternalLinksSection links={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ExternalLinksSection links={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('skips entries whose scheme is not http or https', () => {
    render(
      <ExternalLinksSection
        links={[
          { type: 'other', url: 'javascript:alert(1)' },
          { type: 'other', url: 'data:text/html,<b>x</b>' },
          { type: 'other', url: 'ftp://files.example/doom' },
          { type: 'other', url: 'file:///etc/passwd' },
          { type: 'other', url: 'not a url' },
          { type: 'other', url: 'https://ok.example/' },
          { type: 'other' },
          null,
        ]}
      />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'https://ok.example/' })).toBeInTheDocument();
  });

  it('renders nothing when every entry fails the scheme check', () => {
    const { container } = render(
      <ExternalLinksSection links={[{ type: 'other', url: 'javascript:alert(1)' }]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('puts an unknown type under Other', () => {
    render(<ExternalLinksSection links={[{ type: 'mystery', url: 'https://x.example/' }]} />);
    expect(screen.getByRole('heading', { name: 'Other' })).toBeInTheDocument();
  });

  it('embeds nothing: no iframes, images or media elements', () => {
    const { container } = render(
      <ExternalLinksSection links={[{ type: 'trailer', url: 'https://youtu.be/abc' }]} />,
    );
    expect(container.querySelector('iframe, img, video, audio, embed, object')).toBeNull();
  });
});

describe('isWebUrl', () => {
  it('accepts only http and https', () => {
    expect(isWebUrl('https://a.example')).toBe(true);
    expect(isWebUrl('http://a.example')).toBe(true);
    expect(isWebUrl('HTTPS://a.example')).toBe(true);
    expect(isWebUrl('javascript:alert(1)')).toBe(false);
    expect(isWebUrl('//a.example')).toBe(false);
    expect(isWebUrl(42)).toBe(false);
  });
});
