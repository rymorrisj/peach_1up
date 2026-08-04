import TabbedLayout, { buildTabRoutes } from '@/components/layout/TabbedLayout';
import type { TabConfig } from '@/components/layout/TabbedLayout';
import Games from './Games';
import Media from './Media';
import Apps from './Apps';

const tabs: TabConfig[] = [
  { label: 'Games', segment: 'games', element: <Games /> },
  { label: 'Media', segment: 'media', element: <Media /> },
  { label: 'Apps', segment: 'apps', element: <Apps /> },
];

// Consumed by main.tsx alongside <Software/> to declare the /software/{games,media,apps}
// child routes (+ index/catchall redirects to games) in the same place the app's other routes live.
export const softwareTabRoutes = buildTabRoutes(tabs);

export default function Software() {
  return <TabbedLayout tabs={tabs} title="Software" />;
}
