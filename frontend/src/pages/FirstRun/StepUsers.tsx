interface StepUsersProps {
  onBack: () => void;
  onNext: () => void;
}

export default function StepUsers({ onBack, onNext }: StepUsersProps) {
  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        One household, different permissions
      </h2>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        Peach 1UP supports an owner account plus admins and sub-accounts. Sub-accounts can be
        restricted from specific items or content types, and every account can have its own PIN. Set
        this up now, or add accounts later from Settings, Users.
      </p>

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
          Next: Emulators
        </button>
      </div>
    </section>
  );
}
