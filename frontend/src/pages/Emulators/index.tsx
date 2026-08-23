import TabbedLayout from '@/components/layout/TabbedLayout';
import { emulatorsTabs } from './tabs';

export default function Emulators() {
  return <TabbedLayout tabs={emulatorsTabs} title="Emulators" />;
}
