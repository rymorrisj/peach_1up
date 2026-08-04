import { screen, waitFor, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import MediaDetail from '@/pages/Software/MediaDetail';
import { apiFetch } from '@/api/client';

// Basic smoke coverage only, not exhaustive behavior coverage (that's the
// existing CollectionDetail*.test.tsx depth, planned separately for a full
// audit before beta). This just catches a render-breaks-completely
// regression, same apiFetch-mocking approach as CollectionDetail's tests.
// The edit-form cases below are similarly basic: render, field edit, save
// PATCH body, not the field-by-field depth of CollectionDetail.editform.test.tsx.
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

const plainUser = {
  id: 1,
  name: 'Player',
  is_owner: false,
  is_admin: false,
  pin_required: false,
  can_launch_media: true,
  can_manage_environment: false,
  can_manage_game: false,
  can_manage_media: false,
  can_manage_app: false,
  can_manage_controllerMapping: false,
  can_manage_settings: false,
  can_manage_users: false,
  block_unrated_media: false,
  is_locked: false,
  failed_pin_attempts: 0,
};

function minimalMedia(overrides?: Record<string, unknown>) {
  return {
    id: 1,
    slug: 'my-video',
    title: 'My Video',
    description: null,
    tags: [],
    linked_items: [],
    media_kind: 'video',
    cover_art_path: null,
    cover_art_url: null,
    items: [
      {
        id: 100,
        media_item_bundle_id: 1,
        file_path: '/media/video.mp4',
        cover_art_path: null,
        cover_art_url: null,
      },
    ],
    ...overrides,
  };
}

interface RecordedCall {
  url: string;
  method?: string;
  body?: unknown;
}

function mockApi(media: unknown) {
  const calls: RecordedCall[] = [];
  vi.mocked(apiFetch).mockImplementation((url: unknown, init?: unknown) => {
    if (typeof url !== 'string') return Promise.resolve([]);
    const method = (init as { method?: string } | undefined)?.method;
    const bodyRaw = (init as { body?: string } | undefined)?.body;
    calls.push({ url, method, body: bodyRaw ? JSON.parse(bodyRaw) : undefined });
    if (url === '/api/v1/auth/me') return Promise.resolve(plainUser);
    if (url === '/api/v1/auth/refresh') return Promise.resolve({ user: plainUser });
    if (url === '/api/v1/media-item-bundle/1' && (!method || method === 'GET'))
      return Promise.resolve(media);
    if (url === '/api/v1/media-item-bundle/1' && method === 'PATCH') return Promise.resolve({});
    return Promise.resolve([]);
  });
  return calls;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/software/media/1']}>
      <QueryClientProvider client={queryClient}>
        <AppProvider>
          <Routes>
            <Route path="/software/media/:id" element={<MediaDetail />} />
          </Routes>
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('MediaDetail', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('renders without throwing given a minimal media fixture', async () => {
    mockApi(minimalMedia());
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('My Video')[0]).toBeInTheDocument();
    });
  });

  describe('edit form', () => {
    it('renders the edit form pre-filled from the entity', async () => {
      mockApi(minimalMedia({ title: 'My Video', description: 'A cool video' }));
      renderPage();

      await waitFor(() => {
        expect(screen.getByLabelText('Title')).toHaveValue('My Video');
      });
      expect(screen.getByLabelText('Description')).toHaveValue('A cool video');
    });

    it('updates local state when a field is edited', async () => {
      const user = userEvent.setup();
      mockApi(minimalMedia());
      renderPage();

      const title = await screen.findByLabelText('Title');
      await user.clear(title);
      await user.type(title, 'Renamed Video');

      expect(title).toHaveValue('Renamed Video');
    });

    it('sends the expected PATCH body on save', async () => {
      const user = userEvent.setup();
      const calls = mockApi(minimalMedia());
      renderPage();

      const title = await screen.findByLabelText('Title');
      await user.clear(title);
      await user.type(title, 'Renamed Video');
      await user.click(screen.getByRole('button', { name: 'Save Changes' }));

      await waitFor(() => {
        const patch = calls.find(
          (c) => c.url === '/api/v1/media-item-bundle/1' && c.method === 'PATCH',
        );
        expect(patch).toBeTruthy();
        expect(patch?.body).toMatchObject({
          title: 'Renamed Video',
          description: null,
          cover_art_path: null,
        });
      });
    });
  });
});
