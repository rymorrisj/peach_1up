import { useParams } from 'react-router-dom'

export default function Detail() {
  const { id } = useParams<{ id: string }>()

  return (
    <>
      <h1 className="mb-6 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Library Item
      </h1>
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Item #{id} — detail view coming soon.
      </p>
    </>
  )
}
