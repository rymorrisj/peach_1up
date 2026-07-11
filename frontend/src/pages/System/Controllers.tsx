import EmptyState from '@/components/common/EmptyState'

// Pure placeholder — no model, no list/detail behavior (dev_docs/v2/08, decision 8/15).
export default function Controllers() {
  return (
    <div className="p-6">
      <EmptyState heading="Controllers" subtext="Coming soon." />
    </div>
  )
}
