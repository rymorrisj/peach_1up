import type { ReactNode } from 'react'
// import { Moon, Sun } from 'lucide-react'  // re-enable with theme toggle
import { useQuery } from '@tanstack/react-query'
import { useAppContext } from '@/context/useAppContext'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'
type LaunchHistory = components['schemas']['LaunchHistoryRead']

interface TopBarProps {
  title?: string
  children?: ReactNode
}

export default function TopBar({ title, children }: TopBarProps) {
  const { state, dispatch: _dispatch } = useAppContext()

  const { data: launches = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches'],
    queryFn: () => apiFetch<LaunchHistory[]>('/api/v1/launches'),
    enabled: !!state.activeUser,
    // Only keep polling while a launch is actually running — once every
    // launch has ended_at set, stop refetching instead of hitting the
    // endpoint on a fixed timer forever.
    refetchInterval: (query) => {
      const data = query.state.data ?? []
      return data.some((l) => l.ended_at === null) ? 5000 : false
    },
    refetchOnWindowFocus: false,
  })

  const activeSessions = launches.filter((l) => l.ended_at === null).length

  return (
    <header
      className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-3 px-6"
      style={{
        borderBottom: '1px solid var(--border)',
        background: 'var(--topbar-glass)',
        backdropFilter: 'blur(20px) saturate(1.4)',
      }}
    >
      {title && (
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: 18,
            letterSpacing: '-0.01em',
            margin: 0,
            color: 'var(--fg-1)',
          }}
        >
          {title}
        </h1>
      )}
      {children}
      <div className="flex flex-1 items-center justify-end gap-3">
        {activeSessions > 0 && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
            style={{
              background: 'rgb(110 208 154 / 0.12)',
              color: 'var(--success)',
              border: '1px solid rgb(110 208 154 / 0.3)',
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: 'var(--success)', animation: 'dot-pulse 1.4s ease-in-out infinite' }}
              aria-hidden="true"
            />
            {activeSessions} running
          </span>
        )}
        {/* TODO: theme toggle is disabled until light mode is fixed
        // restore: import { Moon, Sun }; rename _dispatch→dispatch, _isDark→isDark
        <button
          type="button"
          onClick={() => _dispatch({ type: 'SET_THEME', payload: _isDark ? 'light' : 'dark' })}
          aria-label={_isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors duration-[120ms]"
          style={{ color: 'var(--fg-2)', border: '1px solid transparent' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--surface-2)'
            e.currentTarget.style.color = 'var(--fg-1)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'var(--fg-2)'
          }}
        >
          {_isDark ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
        </button>
        */}
      </div>
    </header>
  )
}
