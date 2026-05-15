import { cn } from '@/lib/utils'

interface Tab<T extends string> {
  id: T
  label: string
}

interface TabBarProps<T extends string> {
  tabs: Tab<T>[]
  activeTab: T
  onTabChange: (tab: T) => void
}

export default function TabBar<T extends string>({ tabs, activeTab, onTabChange }: TabBarProps<T>) {
  return (
    <div className="mb-6 flex border-b border-neutral-200 dark:border-neutral-800">
      {tabs.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          onClick={() => onTabChange(id)}
          className={cn(
            '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
            activeTab === id
              ? 'border-[#ff8a5c] text-[#ff8a5c]'
              : 'border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300',
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
