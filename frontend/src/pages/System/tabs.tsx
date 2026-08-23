import type { TabConfig } from '@/components/layout/TabbedLayout';
import { buildTabRoutes } from '@/components/layout/buildTabRoutes';
import Health from './Health';
import Controllers from './Controllers';

export const systemTabs: TabConfig[] = [
  { label: 'Health', segment: 'health', element: <Health /> },
  { label: 'Controllers', segment: 'controllers', element: <Controllers /> },
];

// Consumed by main.tsx alongside <System/> to declare the /system/{health,controllers}
// child routes (+ index/catchall redirects to health) in the same place the app's other routes live.
export const systemTabRoutes = buildTabRoutes(systemTabs);
