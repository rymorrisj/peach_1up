const DOCS_BASE_URL =
  (import.meta.env.VITE_DOCS_BASE_URL as string | undefined) ?? 'http://localhost:3000'

interface StepGuidesProps {
  onBack: () => void
  onFinish: () => void
  finishing: boolean
}

export default function StepGuides({ onBack, onFinish, finishing }: StepGuidesProps) {
  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        You're set up
      </h2>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        This was a brief introduction to get you started. Peach 1UP has real depth behind it,
        metadata fetching, tagging, restrictions, snapshots, and more. Please take a look through
        the Guides section when you have a moment. It's worth the read.
      </p>

      <div className="mb-8">
        <a
          href={`${DOCS_BASE_URL}/docs/user-guide`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-accent hover:underline"
        >
          Take me to Guides →
        </a>
      </div>

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={onBack}
          disabled={finishing}
          className="text-sm text-neutral-400 hover:text-neutral-600 disabled:opacity-40 dark:text-neutral-500 dark:hover:text-neutral-300"
        >
          Back
        </button>
        <button
          type="button"
          onClick={onFinish}
          disabled={finishing}
          className="rounded-md bg-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {finishing ? 'Finishing…' : 'Finish'}
        </button>
      </div>
    </section>
  )
}
