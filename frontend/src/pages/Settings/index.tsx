import { useState } from 'react'
import TopBar from '@/components/layout/TopBar'
import TabBar from '@/components/common/TabBar'
import GeneralTab from '@/pages/Settings/GeneralTab'
import UsersTab from '@/pages/Settings/UsersTab'
import AttributionTab from '@/pages/Settings/AttributionTab'
import AdvancedTab from '@/pages/Settings/AdvancedTab'

type Tab = 'general' | 'users' | 'attribution' | 'advanced'

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'users', label: 'Users' },
  { id: 'attribution', label: 'Attribution' },
  { id: 'advanced', label: 'Advanced' },
]

export default function Settings() {
  const [activeTab, setActiveTab] = useState<Tab>('general')

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Settings" />
      <div className="p-6">
        <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
        {activeTab === 'general' && <GeneralTab />}
        {activeTab === 'users' && <UsersTab />}
        {activeTab === 'attribution' && <AttributionTab />}
        {activeTab === 'advanced' && <AdvancedTab />}
      </div>
    </div>
  )
}
