import React from 'react'
import { render } from '@testing-library/react'
import type { RenderResult } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import type { components } from '@shared/types'
type LibraryCollection = components['schemas']['LibraryCollectionRead']

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

export function renderWithProviders(ui: React.ReactElement): RenderResult {
  const queryClient = createTestQueryClient()
  return render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(AppProvider, null, ui),
    ),
  )
}

// Builds a collection-of-one (single leaf) — the unified library read shape.
export function createMockLibraryItem(overrides?: Partial<LibraryCollection>): LibraryCollection {
  const base = {
    id: 1,
    slug: 'test-game',
    title: 'Test Game',
    era: 'dos',
    launch_count: 0,
    launch_review_flagged: false,
    installed: false,
    requires_install: false,
    launch_disk_id: 100,
    display_disk_id: 100,
    tags: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  } as LibraryCollection
  // Provide a single leaf so CollectionCard/CollectionDetail can render, unless
  // the caller supplied their own items array.
  if (!('items' in (overrides ?? {}))) {
    base.items = [
      {
        id: 100,
        library_collection_id: base.id,
        disc_number: 1,
        media_path: '/images/test.iso',
        cover_art_url: null,
      },
    ] as LibraryCollection['items']
  }
  return base
}

export const createMockCollection = createMockLibraryItem
