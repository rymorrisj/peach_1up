import { Library as LibraryIcon } from 'lucide-react'
import EmptyState from '@/components/common/EmptyState'

export default function Library() {
  return (
    <>
      <h1 className="mb-6 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Library
      </h1>
      <EmptyState
        icon={<LibraryIcon size={48} />}
        heading="No items in your library yet"
        subtext="Add a game or application to get started."
      />
    </>
  )
}
