import React from 'react';
import { render } from '@testing-library/react';
import type { RenderResult } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppContext, appReducer, initialState } from '@/context/_AppContext';
import { ToastProvider } from '@/ui/ToastProvider';
import type { components } from '@shared/types';
type LibraryCollection = components['schemas']['GameItemBundleRead'];
type SessionUser = components['schemas']['SessionUserRead'];

export const TEST_USER: SessionUser = {
  id: 1,
  name: 'Test User',
  is_owner: false,
  pin_required: false,
  can_launch_media: true,
  can_manage_environment: false,
  can_manage_game: false,
  can_manage_media: false,
  can_manage_app: false,
  can_manage_controllerMapping: false,
  can_manage_settings: false,
  can_manage_users: false,
  is_admin: false,
  block_unrated_media: false,
  is_locked: false,
  failed_pin_attempts: 0,
  is_host: false,
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

// Supplies the app context directly so no test depends on a real /auth/me call.
function TestAppProvider({
  activeUser,
  children,
}: {
  activeUser: SessionUser | null;
  children: React.ReactNode;
}) {
  const [state, dispatch] = React.useReducer(appReducer, {
    ...initialState,
    activeUser,
    authChecked: true,
  });
  return React.createElement(AppContext.Provider, { value: { state, dispatch } }, children);
}

// activeUser defaults to a signed-in TEST_USER. Pass null to render signed out.
export function renderWithProviders(
  ui: React.ReactElement,
  { activeUser = TEST_USER }: { activeUser?: SessionUser | null } = {},
): RenderResult {
  const queryClient = createTestQueryClient();
  return render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(
        ToastProvider,
        null,
        React.createElement(TestAppProvider, { activeUser }, ui),
      ),
    ),
  );
}

// Builds a collection-of-one (single leaf), the unified library read shape.
export function createMockLibraryItem(overrides?: Partial<LibraryCollection>): LibraryCollection {
  const base = {
    id: 1,
    slug: 'test-game',
    title: 'Test Game',
    platform: 'dos',
    launch_count: 0,
    launch_review_flagged: false,
    installed: false,
    requires_install: false,
    launch_disk_id: 100,
    display_disk_id: 100,
    tags: [],
    linked_items: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  } as LibraryCollection;
  // Provide a single leaf so CollectionCard/CollectionDetail can render, unless
  // the caller supplied their own items array.
  if (!('items' in (overrides ?? {}))) {
    base.items = [
      {
        id: 100,
        game_item_bundle_id: base.id,
        disc_number: 1,
        media_path: '/images/test.iso',
        cover_art_url: null,
      },
    ] as LibraryCollection['items'];
  }
  return base;
}

export const createMockCollection = createMockLibraryItem;
