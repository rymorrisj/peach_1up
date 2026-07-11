import EmptyState from '@/components/common/EmptyState'

// Temporary stub, NOT the doc-03/08 intent (Media is supposed to reuse the
// Games list+detail shape). Left as a placeholder this pass because building
// the real thing hit two blockers outside this session's routing+titles
// scope — see the session summary for details.
export default function Media() {
  return (
    <div className="p-6">
      <EmptyState heading="Media" subtext="Coming soon." />
    </div>
  )
}
