import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UploadBody from './UploadBody';
import { chunkedUpload } from '@/lib/chunkedUpload';
import type { LibraryModalConfig } from './types';

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(() => Promise.resolve({})),
  ApiError: class ApiError extends Error {},
}));
vi.mock('@/lib/chunkedUpload', () => ({
  chunkedUpload: vi.fn(() => ({ promise: new Promise(() => {}), abort: vi.fn() })),
}));
vi.mock('@/context/useAppContext', () => ({
  useAppContext: () => ({ state: { backgroundJobs: [] }, dispatch: vi.fn() }),
}));

const mediaConfig: LibraryModalConfig = {
  mode: 'upload',
  uploadDomain: 'software_media',
  modalTitle: 'Add Media',
  entityLabel: 'media',
  entityLabelPlural: 'media',
};

function renderBody(config: LibraryModalConfig) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <UploadBody open onClose={() => {}} onComplete={() => {}} config={config} />
    </QueryClientProvider>,
  );
}

function pick(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files } });
}

describe('UploadBody media archive kind', () => {
  beforeEach(() => vi.mocked(chunkedUpload).mockClear());

  it('holds an archive back and asks for its kind', () => {
    renderBody(mediaConfig);

    pick([new File(['x'], 'scans.zip')]);

    expect(chunkedUpload).not.toHaveBeenCalled();
    expect(screen.getByText('What does this archive contain?')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Upload' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it('uploads a non-archive straight away with no kind', () => {
    renderBody(mediaConfig);

    pick([new File(['x'], 'theme.mp3')]);

    expect(chunkedUpload).toHaveBeenCalledTimes(1);
    expect(vi.mocked(chunkedUpload).mock.calls[0][7]).toBeUndefined();
    expect(screen.queryByText('What does this archive contain?')).toBeNull();
  });

  it('drops a held archive when Cancel is pressed', () => {
    renderBody(mediaConfig);
    pick([new File(['x'], 'scans.7z')]);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText('scans.7z')).toBeNull();
    expect(chunkedUpload).not.toHaveBeenCalled();
  });

  it('does not hold archives for other domains', () => {
    renderBody({ ...mediaConfig, uploadDomain: 'software_games' });

    pick([new File(['x'], 'game.zip')]);

    expect(chunkedUpload).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('What does this archive contain?')).toBeNull();
  });
});
