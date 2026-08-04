import * as Tabs from '@radix-ui/react-tabs';
import TopBar from '@/components/layout/TopBar';
import TabBar from '@/components/common/TabBar';
import AttributionTab from '@/pages/Settings/AttributionTab';
import AdvancedTab from '@/pages/Settings/AdvancedTab';

type Tab = 'attribution' | 'advanced';

const TABS: { id: Tab; label: string }[] = [
  { id: 'attribution', label: 'Attribution' },
  { id: 'advanced', label: 'Advanced' },
];

export default function Settings() {
  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Settings" />
      <div className="p-6">
        <Tabs.Root defaultValue="attribution">
          <TabBar tabs={TABS} />
          <Tabs.Content value="attribution">
            <AttributionTab />
          </Tabs.Content>
          <Tabs.Content value="advanced">
            <AdvancedTab />
          </Tabs.Content>
        </Tabs.Root>
      </div>
    </div>
  );
}
