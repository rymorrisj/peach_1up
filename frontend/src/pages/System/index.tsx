import TabbedLayout, { buildTabRoutes } from '@/components/layout/TabbedLayout';
import type { TabConfig } from '@/components/layout/TabbedLayout';
import Health from './Health';
import Controllers from './Controllers';

const tabs: TabConfig[] = [
  { label: 'Health', segment: 'health', element: <Health /> },
  { label: 'Controllers', segment: 'controllers', element: <Controllers /> },
];

// Consumed by main.tsx alongside <System/> to declare the /system/{health,controllers}
// child routes (+ index/catchall redirects to health) in the same place the app's other routes live.
export const systemTabRoutes = buildTabRoutes(tabs);

export default function System() {
  return <TabbedLayout tabs={tabs} title="System" />;
}
