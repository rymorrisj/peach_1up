interface Step1WelcomeProps {
  onNext: () => void
}

export default function Step1Welcome({ onNext }: Step1WelcomeProps) {
  return (
    <section className="text-center">
      <h1 className="mb-4 text-3xl font-semibold text-neutral-900 dark:text-neutral-100">
        Welcome to Peach 1UP
      </h1>
      <p className="mb-3 text-base text-neutral-600 dark:text-neutral-400">
        Peach 1UP is a preservation launcher. Point it at a disk image, pick an
        era, and the right emulator launches automatically — no manual
        configuration required.
      </p>
      <p className="mb-10 text-sm text-neutral-500 dark:text-neutral-500">
        This wizard will guide you through detecting your emulators, setting
        your library paths, and creating your owner profile.
      </p>
      <button
        type="button"
        onClick={onNext}
        className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
      >
        Get Started
      </button>
    </section>
  )
}
