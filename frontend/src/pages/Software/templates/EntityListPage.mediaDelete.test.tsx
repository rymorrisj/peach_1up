import { screen, waitFor, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import { apiFetch } from '@/api/client';
import { EntityListPage } from './EntityListPage';
import { describeMediaDelete, mediaDomainConfig } from '../configs/mediaConfig';

// Media delete (MED-17) uses the same confirm dialog and token flow as Game
// delete, seeded from the existing delete_media_on_removal setting, and the
// dialog names what will be removed from the server's delete preview.
vi.mock('@/api/client', () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.name = 'ApiError';
    }
  },
}));

const PREVIEW = {
  file_count: 2,
  removable_file_count: 1,
  game_cover_count: 1,
  app_cover_count: 0,
  media_cover_count: 0,
};

function mediaBundle() {
  return {
    id: 7,
    slug: 'doom-art',
    title: 'Doom Art',
    description: null,
    tags: [],
    media_kind: 'image',
    cover_art_path: null,
    cover_art_url: null,
    content_rating: null,
    effective_content_rating: null,
    is_inherited: false,
    linked_items: [],
    items: [],
  };
}

interface RecordedCall {
  url: string;
  method: string;
}

function mockApi(options: {
  deleteMediaOnRemoval: boolean;
  previewFails?: boolean;
}): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: RequestInit) => {
    const u = typeof url === 'string' ? url : '';
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ url: u, method });
    if (u.startsWith('/api/v1/media-item-bundles')) {
      return Promise.resolve({ items: [mediaBundle()], total: 1, limit: 50, offset: 0 });
    }
    if (u === '/api/v1/settings/library-defaults') {
      return Promise.resolve({
        delete_media_on_removal: options.deleteMediaOnRemoval,
        delete_original_on_upload: false,
      });
    }
    if (u === '/api/v1/media-item-bundle/7/delete-preview') {
      return options.previewFails
        ? Promise.reject(new Error('preview failed'))
        : Promise.resolve(PREVIEW);
    }
    if (method === 'POST' && u.endsWith('/confirm-delete')) {
      return Promise.resolve({ confirmation_token: 'tok' });
    }
    if (method === 'DELETE') return Promise.resolve(undefined);
    return Promise.resolve([]);
  });
  return calls;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <EntityListPage config={mediaDomainConfig} />
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function openRemoveDialog(user: ReturnType<typeof userEvent.setup>, calls: RecordedCall[]) {
  await waitFor(() => expect(screen.getAllByText('Doom Art').length).toBeGreaterThan(0));
  await waitFor(() =>
    expect(calls.some((c) => c.url === '/api/v1/settings/library-defaults')).toBe(true),
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  await user.click(screen.getByRole('button', { name: 'Remove Doom Art' }));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
}

describe('Media delete dialog', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('names the files and covers the delete removes', async () => {
    const user = userEvent.setup();
    const calls = mockApi({ deleteMediaOnRemoval: false });
    renderPage();

    await openRemoveDialog(user, calls);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('1 of 2 files will be deleted from disk');
    expect(dialog).toHaveTextContent('1 file stays');
    expect(dialog).toHaveTextContent('1 game disc');
    expect(
      screen.getByRole('checkbox', { name: /also delete media files from disk/i }),
    ).toBeInTheDocument();
  });

  it('seeds the checkbox from delete_media_on_removal and sends it with the token', async () => {
    const user = userEvent.setup();
    const calls = mockApi({ deleteMediaOnRemoval: true });
    renderPage();

    await openRemoveDialog(user, calls);
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: /also delete media files from disk/i }),
      ).toBeChecked(),
    );
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      const issued = calls.find((c) => c.method === 'POST' && c.url.endsWith('/confirm-delete'));
      expect(issued?.url).toBe('/api/v1/media-item-bundle/7/confirm-delete');
      const del = calls.find((c) => c.method === 'DELETE');
      expect(del?.url).toBe('/api/v1/media-item-bundle/7?confirmation_token=tok&delete_media=true');
    });
  });

  it('sends delete_media=false when the box is unchecked', async () => {
    const user = userEvent.setup();
    const calls = mockApi({ deleteMediaOnRemoval: true });
    renderPage();

    await openRemoveDialog(user, calls);
    const box = screen.getByRole('checkbox', { name: /also delete media files from disk/i });
    await waitFor(() => expect(box).toBeChecked());
    await user.click(box);
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      const del = calls.find((c) => c.method === 'DELETE');
      expect(del?.url).toBe(
        '/api/v1/media-item-bundle/7?confirmation_token=tok&delete_media=false',
      );
    });
  });

  it('cancelling sends nothing', async () => {
    const user = userEvent.setup();
    const calls = mockApi({ deleteMediaOnRemoval: true });
    renderPage();

    await openRemoveDialog(user, calls);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(calls.some((c) => c.method === 'DELETE' || c.url.endsWith('/confirm-delete'))).toBe(
      false,
    );
  });

  it('opens no dialog and deletes nothing when the preview fails', async () => {
    const user = userEvent.setup();
    const calls = mockApi({ deleteMediaOnRemoval: true, previewFails: true });
    renderPage();

    await waitFor(() => expect(screen.getAllByText('Doom Art').length).toBeGreaterThan(0));
    await user.click(screen.getByRole('button', { name: 'Remove Doom Art' }));

    await waitFor(() =>
      expect(calls.some((c) => c.url === '/api/v1/media-item-bundle/7/delete-preview')).toBe(true),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText(/will be deleted from disk/)).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === 'DELETE' || c.url.endsWith('/confirm-delete'))).toBe(
      false,
    );
  });
});

describe('describeMediaDelete', () => {
  it('says when there are no files', () => {
    expect(
      describeMediaDelete({
        file_count: 0,
        removable_file_count: 0,
        game_cover_count: 0,
        app_cover_count: 0,
        media_cover_count: 0,
      }),
    ).toBe('It has no files.');
  });

  it('says no covers are affected when none use the files', () => {
    const text = describeMediaDelete({
      file_count: 1,
      removable_file_count: 1,
      game_cover_count: 0,
      app_cover_count: 0,
      media_cover_count: 0,
    });
    expect(text).toContain('1 of 1 file will be deleted from disk');
    expect(text).toContain('No game or other media uses these files as cover art.');
    expect(text).toContain('Unchecked, the files and every cover stay as they are.');
  });

  it('pluralises kept files and covers', () => {
    const text = describeMediaDelete({
      file_count: 5,
      removable_file_count: 2,
      game_cover_count: 2,
      app_cover_count: 1,
      media_cover_count: 1,
    });
    expect(text).toContain('3 files stay because other items use them');
    expect(text).toContain('2 game discs, 1 app and 1 other media item');
  });
});
