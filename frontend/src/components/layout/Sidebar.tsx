import { NavLink } from 'react-router-dom'
import { Library, Settings, BookOpen, ChevronLeft, ChevronRight, Cpu, Monitor } from 'lucide-react'
import { useAppContext } from '@/context/AppContext'

const NAV_ITEMS = [
  { to: '/library', label: 'Library', Icon: Library, activeLaunchType: 'library_item' as const },
  { to: '/environments', label: 'Environments', Icon: Monitor, activeLaunchType: 'environment' as const },
  { to: '/emulators', label: 'Emulators', Icon: Cpu },
  { to: '/settings', label: 'Settings', Icon: Settings },
  { to: '/guides', label: 'Guides', Icon: BookOpen },
] as const

export default function Sidebar() {
  const { state, dispatch } = useAppContext()
  const collapsed = state.sidebarCollapsed

  return (
    <aside
      id="main-sidebar"
      className={`flex flex-col shrink-0 border-r border-neutral-200 bg-neutral-50 transition-all duration-200 dark:border-surface-400 dark:bg-surface-900 ${
        collapsed ? 'w-14' : 'w-56'
      }`}
    >
      <nav className="flex-1 py-[0.75em]" aria-label="Main navigation">
        <ul role="list" className="space-y-[0.25em] px-[0.5em]">
          {NAV_ITEMS.map(({ to, label, Icon, ...rest }) => {
            const activeLaunchType = 'activeLaunchType' in rest ? rest.activeLaunchType : undefined
            const hasActiveLaunch = activeLaunchType
              ? Array.from(state.activeLaunches.values()).some(
                  (e) => e.target_type === activeLaunchType && e.ended_at === null,
                )
              : false

            return (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-[0.75em] rounded-md px-[0.75em] py-[0.5em] text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-neutral-200 text-peach dark:bg-surface-700 dark:text-peach'
                        : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-surface-800 dark:hover:text-neutral-100'
                    }`
                  }
                  aria-label={collapsed ? label : undefined}
                >
                  <span className="relative shrink-0">
                    <Icon size={18} aria-hidden="true" />
                    {hasActiveLaunch && (
                      <span
                        className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-green-500"
                        aria-hidden="true"
                      />
                    )}
                  </span>
                  {!collapsed && <span>{label}</span>}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="px-[0.5em] pb-[0.75em]">
        <button
          type="button"
          onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
          aria-expanded={!collapsed}
          aria-controls="main-sidebar"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex w-full items-center justify-center rounded-md px-[0.75em] py-[0.5em] text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-surface-800 dark:hover:text-neutral-100"
        >
          {collapsed ? (
            <ChevronRight size={18} aria-hidden="true" />
          ) : (
            <ChevronLeft size={18} aria-hidden="true" />
          )}
        </button>
      </div>
    </aside>
  )
}
