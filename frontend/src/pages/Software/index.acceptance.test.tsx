/**
 * Acceptance test: Software page
 *
 * Renders the full page with all real child components.
 * Only the network boundary (apiFetch) is mocked.
 *
 * User flow: page loads with library items → user opens the Add Media modal
 * → modal is visible with the file drop/upload zone.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import Games from '@/pages/Software/Games';
import { apiFetch } from '@/api/client';
import { createMockLibraryItem } from '@/test/helpers';

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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AppProvider>
            <Games />
          </AppProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Software acceptance', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows library items then opens the Add Media modal on button click', async () => {
    const user = userEvent.setup();
    const items = [
      createMockLibraryItem({ id: 1, title: 'Doom', era: 'dos', slug: 'doom' }),
      createMockLibraryItem({ id: 2, title: 'Ultima VII', era: 'dos', slug: 'ultima-vii' }),
    ];
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.includes('/api/v1/game-items')) {
        return Promise.resolve({ items, total: items.length, limit: 50, offset: 0 });
      }
      return Promise.resolve([]);
    });

    renderPage();

    // Primary content appears
    await waitFor(() => {
      // Title appears in both the art placeholder and the card label
      expect(screen.getAllByText('Doom').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Ultima VII').length).toBeGreaterThanOrEqual(1);
    });

    // User clicks the Add button. Post-EntityListPage-cutover copy: the
    // TopBar button label is now generic "+ Add {entityLabel}" (see
    // templates/EntityListPage.tsx), replacing the old bespoke Games.tsx-only
    // "+ Add Media" label. The modal it opens still has "Add Media" as its
    // title (gameUploadModalConfig.modalTitle), matched separately below.
    await user.click(screen.getByRole('button', { name: /add game/i }));

    // The modal should be open and contain the drag-and-drop upload zone
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/drag and drop files here/i)).toBeInTheDocument();
    });
  });

  it('shows the empty state when the library has no items', async () => {
    vi.mocked(apiFetch).mockResolvedValue([]);
    renderPage();
    // Post-EntityListPage-cutover copy, see the comment in the test above.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /no games yet/i })).toBeInTheDocument();
    });
    // Add CTA inside the empty state is also present
    expect(screen.getAllByRole('button', { name: /add game/i }).length).toBeGreaterThanOrEqual(1);
  });
});
