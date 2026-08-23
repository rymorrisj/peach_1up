import type { ReactNode } from 'react';
import { Navigate, Route } from 'react-router-dom';
import type { TabConfig } from './TabbedLayout';

/**
 * Builds the child `<Route>` elements for a section mounted with `TabbedLayout`,
 * from the same `tabs` config passed to the component, so the tab bar and the
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
  const visibleTabs = tabs.filter((tab) => tab.visible !== false);
  const defaultSegment = visibleTabs[0]?.segment;
  const routes: ReactNode[] = visibleTabs.map((tab) => (
    <Route key={tab.segment} path={tab.segment} element={tab.element} />
  ));
  if (defaultSegment) {
    routes.push(
      <Route
        key="__tabbed-layout-index"
        index
        element={<Navigate to={defaultSegment} replace />}
      />,
    );
    routes.push(
      <Route
        key="__tabbed-layout-catchall"
        path="*"
        element={<Navigate to={defaultSegment} replace />}
      />,
    );
  }
  return routes;
}
