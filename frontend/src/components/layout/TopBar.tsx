import { Moon, Sun } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAppContext } from '@/context/AppContext'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'
type LaunchHistory = components['schemas']['LaunchHistoryRead']

export default function TopBar() {
  const { state, dispatch } = useAppContext()
  const isDark = state.theme === 'dark'

  const { data: launches = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches'],
    queryFn: () => apiFetch<LaunchHistory[]>('/api/v1/launches'),
    refetchInterval: 5000,
    refetchOnWindowFocus: false,
  })

  const activeSessions = launches.filter((l) => l.ended_at === null).length

  return (
    <header className="flex h-14 shrink-0 items-center border-b border-neutral-200 bg-neutral-50 px-[1em] dark:border-surface-400 dark:bg-surface-900">
      <span className="font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
        Peach 1UP
      </span>

      <div className="flex flex-1 items-center justify-center gap-3 text-sm">
        {activeSessions > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" aria-hidden="true" />
            {activeSessions} running
          </span>
        )}
        {state.activeProfileId != null && (
          <span className="font-medium text-neutral-500 dark:text-neutral-400">
            Profile {state.activeProfileId}
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={() => dispatch({ type: 'SET_THEME', payload: isDark ? 'light' : 'dark' })}
        aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        className="rounded-md p-[0.5em] text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-surface-800 dark:hover:text-neutral-100"
      >
        {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
      </button>
    </header>
  )
}
