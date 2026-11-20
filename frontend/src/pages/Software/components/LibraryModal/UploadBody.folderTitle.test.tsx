import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UploadBody from './UploadBody';
import type { LibraryModalConfig } from './types';

vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(() => Promise.resolve({})),
  ApiError: class ApiError extends Error {},
}));
vi.mock('@/lib/chunkedUpload', () => ({ chunkedUpload: vi.fn() }));
vi.mock('@/context/useAppContext', () => ({
  useAppContext: () => ({ state: { backgroundJobs: [] }, dispatch: vi.fn() }),
}));

const config: LibraryModalConfig = {
  mode: 'upload',
  uploadDomain: 'games',
  modalTitle: 'Add Media',
  entityLabel: 'game',
  entityLabelPlural: 'games',
  supportsFolderMode: true,
};

function makeFile(name: string, relPath: string): File {
  const file = new File(['x'], name);
  Object.defineProperty(file, 'webkitRelativePath', { value: relPath });
  return file;
}

function armoredCore(): File[] {
  return [
    makeFile('Armored Core (USA).chd', 'Armored Core/Armored Core (USA).chd'),
    makeFile('cover.jpg', 'Armored Core/cover.jpg'),
  ];
}

function renderBody() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <UploadBody open onClose={() => {}} onComplete={() => {}} config={config} />
    </QueryClientProvider>,
  );
}

async function enableFolderMode() {
  await userEvent.click(screen.getByLabelText('Folder upload'));
}

function pickFolder(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files } });
}

function titleInput(): HTMLInputElement {
  return screen.getByPlaceholderText(/Title \(e\.g\./) as HTMLInputElement;
}

function uploadButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Upload Folder' }) as HTMLButtonElement;
}

describe('UploadBody folder upload title', () => {
  it('pre-fills the title after a folder is selected', async () => {
    renderBody();
    await enableFolderMode();
    expect(titleInput().value).toBe('');

    pickFolder(armoredCore());

    expect(titleInput().value).toBe('Armored Core (USA)');
  });

  it('does not overwrite a title the user typed', async () => {
    renderBody();
    await enableFolderMode();
    await userEvent.type(titleInput(), 'My Own Title');

    pickFolder(armoredCore());

    expect(titleInput().value).toBe('My Own Title');
  });

  it('replaces a previous auto-default on re-selection', async () => {
    renderBody();
    await enableFolderMode();
    pickFolder(armoredCore());
    pickFolder([makeFile('Other.iso', 'Other Dir/Other.iso')]);

    expect(titleInput().value).toBe('Other');
  });

  it('enables Upload Folder after selection and disables it when the title is cleared', async () => {
    renderBody();
    await enableFolderMode();
    expect(uploadButton().disabled).toBe(true);

    pickFolder(armoredCore());
    expect(uploadButton().disabled).toBe(false);

    await userEvent.clear(titleInput());
    expect(uploadButton().disabled).toBe(true);
  });
});
