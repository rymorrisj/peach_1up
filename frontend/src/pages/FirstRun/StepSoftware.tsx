interface StepSoftwareProps {
  onNext: () => void;
}

export default function StepSoftware({ onNext }: StepSoftwareProps) {
  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Your library, organized
      </h2>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        Peach 1UP tracks three kinds of Software: Games, Apps, and Media. Each item can carry its
        own era, platform, tags, and restrictions. When you add something, Peach 1UP tries to
        identify it automatically using file signatures and, where possible, cross-checks it against
        known preservation hash databases (Redump, No-Intro) to confirm you have an authentic,
        unmodified copy.
      </p>

      {/* No Back button here, mirrors the original Emulators step's lack of one:
          the step before this is owner account creation, and returning to that
          form mid-flow is not a safe or meaningful action. */}
      <div className="flex items-center justify-end pt-2">
        <button
          type="button"
          onClick={onNext}
          className="rounded-md bg-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Next: Users
        </button>
      </div>
    </section>
  );
}
