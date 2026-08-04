/**
 * Acceptance test: Tags page
 *
 * Renders the full page with all real child components.
 * Only the network boundary (apiFetch) is mocked.
 *
 * User flow: page loads with existing tags → user types a new tag name
 * → the Create Tag button becomes enabled.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import Tags from '@/pages/Tags';
import { apiFetch } from '@/api/client';
import type { components } from '@shared/types';

type TagRead = components['schemas']['TagRead'];

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
        <AppProvider>
          <Tags />
        </AppProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const EXISTING_TAGS: TagRead[] = [
  { id: 1, name: 'adventure', color: 'sky', item_count: 8, is_system: false },
  { id: 2, name: 'strategy', color: 'violet', item_count: 3, is_system: false },
  { id: 3, name: 'Game', color: 'sky', item_count: 0, is_system: true },
];

describe('Tags acceptance', () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it('shows existing tags and enables Create Tag after a name is typed', async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.startsWith('/api/v1/tags')) {
        return Promise.resolve(EXISTING_TAGS);
      }
      return Promise.resolve([]);
    });

    renderPage();

    // Wait for existing tags to appear
    await waitFor(() => {
      // Tag name appears in both the row label and the preview pill
      expect(screen.getAllByText('adventure').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('strategy').length).toBeGreaterThanOrEqual(1);
    });

    // Create Tag button starts disabled (empty input)
    const createBtn = screen.getByRole('button', { name: /create tag/i });
    expect(createBtn).toBeDisabled();

    // User types a new tag name
    const nameInput = screen.getByPlaceholderText(/new tag name/i);
    await user.type(nameInput, 'shooter');

    // Create Tag button is now enabled
    expect(createBtn).not.toBeDisabled();
  });

  it('shows the system tags section with is_system tags from the API', async () => {
    vi.mocked(apiFetch).mockImplementation((url) => {
      if (typeof url === 'string' && url.startsWith('/api/v1/tags')) {
        return Promise.resolve(EXISTING_TAGS);
      }
      return Promise.resolve([]);
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('System tags')).toBeInTheDocument();
      // The seeded system tag renders from the API, not a hardcoded constant.
      expect(screen.getAllByText('Game').length).toBeGreaterThanOrEqual(1);
    });
    // System tags are read-only: no delete control is rendered for them.
    expect(screen.queryByLabelText('Delete tag Game')).not.toBeInTheDocument();
  });
});
