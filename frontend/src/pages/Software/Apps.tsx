import EmptyState from '@/components/common/EmptyState'

// Pure placeholder — no model, no list/detail behavior (dev_docs/v2/08, decision 8).
export default function Apps() {
  return (
    <div className="p-6">
      <EmptyState heading="Apps" subtext="Coming soon." />
    </div>
  )
}
