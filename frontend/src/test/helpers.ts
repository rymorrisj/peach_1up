import React from 'react'
import { render } from '@testing-library/react'
import type { RenderResult } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppProvider } from '@/context/AppContext'
import type { LibraryItem } from '@/types'

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

export function createMockLibraryItem(overrides?: Partial<LibraryItem>): LibraryItem {
  return {
    id: 1,
    title: 'Test Game',
    era: 'dos',
    media_path: '/images/test.iso',
    ...overrides,
  }
}
