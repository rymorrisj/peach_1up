import { useState } from 'react'
import { PageHeader } from '@/ui'
import TabBar from '@/components/common/TabBar'
import GeneralTab from '@/pages/Settings/GeneralTab'
import UsersTab from '@/pages/Settings/UsersTab'
import AttributionTab from '@/pages/Settings/AttributionTab'

type Tab = 'general' | 'users' | 'attribution'

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'users', label: 'Users' },
  { id: 'attribution', label: 'Attribution' },
]

export default function Settings() {
  const [activeTab, setActiveTab] = useState<Tab>('general')

  return (
    <>
      <PageHeader title="Settings" description="Configure library paths and application settings." />
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      {activeTab === 'general' && <GeneralTab />}
      {activeTab === 'users' && <UsersTab />}
      {activeTab === 'attribution' && <AttributionTab />}
    </>
  )
}
