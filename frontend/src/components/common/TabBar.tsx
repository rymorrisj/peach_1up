import * as Tabs from '@radix-ui/react-tabs';

interface Tab<T extends string> {
  id: T;
  label: string;
}

interface TabBarProps<T extends string> {
  tabs: Tab<T>[];
}

// Renders the tab list and triggers only, must be used inside a Radix
// Tabs.Root, the corresponding Tabs.Content panels live with the caller
// since they sit alongside, not inside, this component. Active-tab state is
// owned by the ancestor Tabs.Root (uncontrolled via defaultValue, or
// controlled via value/onValueChange), not by this component.
export default function TabBar<T extends string>({ tabs }: TabBarProps<T>) {
  return (
    <Tabs.List className="mb-6 flex border-b border-neutral-200 dark:border-neutral-800">
      {tabs.map(({ id, label }) => (
        <Tabs.Trigger
          key={id}
          value={id}
          className="-mb-px border-b-2 border-transparent px-4 py-2 text-sm font-medium text-neutral-500 transition-colors hover:text-neutral-700 data-[state=active]:border-accent data-[state=active]:text-accent dark:hover:text-neutral-300"
        >
          {label}
        </Tabs.Trigger>
      ))}
    </Tabs.List>
  );
}
