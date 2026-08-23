import type { ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import TopBar from './TopBar';

export interface TabConfig {
  /** Visible tab label, e.g. "Games". */
  label: string;
  /** Path segment relative to the section mount point, e.g. "games". */
  segment: string;
  /** The collection view mounted for this segment. */
  element: ReactNode;
  /** Defaults to true; set false to hide a tab without unmounting siblings. */
  visible?: boolean;
}

export interface TabbedLayoutProps {
  tabs: TabConfig[];
  /** Page title/header, passed in by the consuming page/section, TabbedLayout
   *  displays it alongside the nav buttons, it does not own or derive it. */
  title: string;
}

/**
 * Domain-agnostic tab bar + `<Outlet/>` for a section's collection sub-routes
 * (Software, Emulators, System, see dev_docs/v2/08_emulator_profiles_navigation.md).
 * The URL is the single source of truth for the active tab: NavLink's own
 * router-driven active-matching is all that's used, no local useState tracks
 * "which tab is active" separately from the route.
 */
export default function TabbedLayout({ tabs, title }: TabbedLayoutProps) {
  const visibleTabs = tabs.filter((tab) => tab.visible !== false);

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
                borderBottom: isActive
                  ? '2px solid rgb(var(--peach-500))'
                  : '2px solid transparent',
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
  );
}

