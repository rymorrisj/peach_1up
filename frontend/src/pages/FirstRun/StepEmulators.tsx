import { Tooltip } from '@/ui'
import type { EmulatorStatus } from './types'

interface StepEmulatorsProps {
  emulators: EmulatorStatus[]
  onNext: () => void
  onSkip: () => void
  onFinishAndGoTo: (target: string) => void
}

export default function StepEmulators({ emulators, onNext, onSkip, onFinishAndGoTo }: StepEmulatorsProps) {
  const required = emulators.filter((e) => e.required)
  const ready = required.filter((e) => e.available).length
  const summary =
    required.length > 0
      ? `${ready} of ${required.length} required emulators ready.`
      : 'No emulators are marked required yet.'

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Emulators
      </h2>
      <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
        Emulators run the software you add to your library, one per platform. Peach 1UP can
        detect installs already on this machine and help you add the rest.
      </p>
      <p className="mb-6 text-sm font-medium text-neutral-700 dark:text-neutral-300">{summary}</p>

      <div className="mb-8 flex items-center gap-3">
        <Tooltip content="Installing and configuring emulators happens on the Emulators page, not here. You can always come back to it later.">
          <span
            tabIndex={0}
            className="cursor-help text-xs text-neutral-400 underline decoration-dotted dark:text-neutral-500"
          >
            Where do I install these?
          </span>
        </Tooltip>
        <button
          type="button"
          onClick={() => onFinishAndGoTo('/emulators')}
          className="text-sm font-medium text-accent hover:underline"
        >
          Finish setup & go to Emulators →
        </button>
      </div>

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={onSkip}
          className="text-sm text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
        >
          Skip setup
        </button>
        <button
          type="button"
          onClick={onNext}
          className="rounded-md bg-accent px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Next: BIOS
        </button>
      </div>
    </section>
  )
}
