import { Moon, Sun } from 'lucide-react'
import { useAppContext } from '@/context/AppContext'

export default function TopBar() {
  const { state, dispatch } = useAppContext()
  const isDark = state.theme === 'dark'

  const activeProfileLabel = state.activeProfileId != null
    ? `Profile ${state.activeProfileId}`
    : null

  return (
    <header className="flex h-14 shrink-0 items-center border-b border-neutral-200 bg-neutral-50 px-[1em] dark:border-surface-400 dark:bg-surface-900">
      <span className="font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
        Peach 1UP
      </span>

      <div className="flex-1 text-center text-sm font-medium text-neutral-500 dark:text-neutral-400">
        {activeProfileLabel}
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
