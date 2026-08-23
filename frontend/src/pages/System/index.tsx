import TabbedLayout from '@/components/layout/TabbedLayout';
import { systemTabs } from './tabs';

export default function System() {
  return <TabbedLayout tabs={systemTabs} title="System" />;
}
