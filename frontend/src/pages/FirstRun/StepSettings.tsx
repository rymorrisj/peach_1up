interface StepSettingsProps {
  onBack: () => void
  onNext: () => void
}

const NOTES = [
  "Deleting is permanent. Removing an item from your library can optionally delete its files too, that action can't be undone, so Peach 1UP always asks first.",
  "Uploads are checked, not just accepted. When you add a file, Peach 1UP hashes it and checks it against known preservation databases where available. A confirmed match means your file matches a verified, authentic copy byte-for-byte. No match doesn't mean something's wrong, it just means we don't have data for it yet.",
]

export default function StepSettings({ onBack, onNext }: StepSettingsProps) {
  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        A few things worth knowing before you start
      </h2>

      <ul className="mb-8 space-y-4">
        {NOTES.map((note) => (
          <li key={note} className="flex gap-3 text-sm text-neutral-500 dark:text-neutral-400">
            <span
              aria-hidden="true"
              className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-neutral-400 dark:bg-neutral-600"
            />
            <span>{note}</span>
          </li>
        ))}
      </ul>

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
        >
          Back
        </button>
        <button
          type="button"
          onClick={onNext}
          className="rounded-md bg-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Next: Guides
        </button>
      </div>
    </section>
  )
}
