interface StepWelcomeProps {
  onNext: () => void
}

export default function StepWelcome({ onNext }: StepWelcomeProps) {
  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Welcome to Peach 1UP
      </h2>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        Peach 1UP is a preservation tool built to make classic PC and console software easy to
        launch and hard to break. Every emulator runs inside its own sandbox, every account has
        its own permissions, and every setting that matters is visible, not hidden behind
        defaults you didn't choose. This quick setup covers the essentials. You can always
        revisit anything from Settings later.
      </p>

      <div className="flex items-center justify-end pt-2">
        <button
          type="button"
          onClick={onNext}
          className="rounded-md bg-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Get Started
        </button>
      </div>
    </section>
  )
}
