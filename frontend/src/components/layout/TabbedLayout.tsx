import type { ReactNode } from 'react'
import { NavLink, Navigate, Outlet, Route } from 'react-router-dom'
import TopBar from './TopBar'

export interface TabConfig {
  /** Visible tab label, e.g. "Games". */
  label: string
  /** Path segment relative to the section mount point, e.g. "games". */
  segment: string
  /** The collection view mounted for this segment. */
  element: ReactNode
  /** Defaults to true; set false to hide a tab without unmounting siblings. */
  visible?: boolean
}

export interface TabbedLayoutProps {
  tabs: TabConfig[]
  /** Page title/header, passed in by the consuming page/section — TabbedLayout
   *  displays it alongside the nav buttons, it does not own or derive it. */
  title: string
}

/**
 * Domain-agnostic tab bar + `<Outlet/>` for a section's collection sub-routes
 * (Software, Emulators, System — see dev_docs/v2/08_emulator_profiles_navigation.md).
 * The URL is the single source of truth for the active tab: NavLink's own
 * router-driven active-matching is all that's used, no local useState tracks
 * "which tab is active" separately from the route.
 */
export default function TabbedLayout({ tabs, title }: TabbedLayoutProps) {
  const visibleTabs = tabs.filter((tab) => tab.visible !== false)

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title={title}>
        <nav className="flex items-center gap-1" aria-label={`${title} sections`}>
          {visibleTabs.map((tab) => (
            <NavLink
              key={tab.segment}
              to={tab.segment}
              style={({ isActive }) => ({
                padding: '10px 14px',
                border: 0,
                background: 'transparent',
                borderBottom: isActive ? '2px solid rgb(var(--peach-500))' : '2px solid transparent',
                color: isActive ? 'rgb(var(--fg-1))' : 'rgb(var(--fg-3))',
                fontFamily: 'var(--font-display)',
                fontWeight: 600,
                fontSize: '0.8125rem',
                lineHeight: 1,
                marginBottom: -1,
                textDecoration: 'none',
              })}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </TopBar>
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}

/**
 * Builds the child `<Route>` elements for a section mounted with `TabbedLayout`,
 * from the same `tabs` config passed to the component — so the tab bar and the
 * routing table are declared once, not duplicated. One route per visible tab,
 * plus an index redirect and a catch-all redirect (both to the first visible
 * tab's segment) so a deep link to a hidden or nonexistent tab lands on the
 * section's default tab instead of rendering a blank `<Outlet/>`.
 *
 * Usage (in whatever module declares the app's routes):
 *
 *   const tabs: TabConfig[] = [...]
 *   <Route path="/emulators" element={<TabbedLayout tabs={tabs} title="Emulators" />}>
 *     {buildTabRoutes(tabs)}
 *   </Route>
 */
export function buildTabRoutes(tabs: TabConfig[]): ReactNode[] {
  const visibleTabs = tabs.filter((tab) => tab.visible !== false)
  const defaultSegment = visibleTabs[0]?.segment
  const routes: ReactNode[] = visibleTabs.map((tab) => (
    <Route key={tab.segment} path={tab.segment} element={tab.element} />
  ))
  if (defaultSegment) {
    routes.push(<Route key="__tabbed-layout-index" index element={<Navigate to={defaultSegment} replace />} />)
    routes.push(<Route key="__tabbed-layout-catchall" path="*" element={<Navigate to={defaultSegment} replace />} />)
  }
  return routes
}
