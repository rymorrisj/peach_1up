import TabbedLayout from '@/components/layout/TabbedLayout';
import { softwareTabs } from './tabs';

export default function Software() {
  return <TabbedLayout tabs={softwareTabs} title="Software" />;
}
