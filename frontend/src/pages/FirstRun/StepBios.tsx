import { useQuery } from '@tanstack/react-query'
import { Tooltip } from '@/ui'
import { apiFetch } from '@/api/client'
import type { Page } from '@/hooks/usePaginatedList'
import type { components } from '@shared/types'

type BiosItem = components['schemas']['BiosItem']

const DOCS_BASE_URL =
  (import.meta.env.VITE_DOCS_BASE_URL as string | undefined) ?? 'http://localhost:3000'

interface StepBiosProps {
  onBack: () => void
  onFinish: () => void
  onFinishAndGoTo: (target: string) => void
  finishing: boolean
}

export default function StepBios({ onBack, onFinish, onFinishAndGoTo, finishing }: StepBiosProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['first-run-bios-summary'],
    queryFn: () => apiFetch<Page<BiosItem>>('/api/v1/bios?limit=200'),
  })

  const required = (data?.items ?? []).filter((b) => b.required)
  const present = required.filter((b) => b.is_present).length

  const summary = isLoading
    ? 'Checking BIOS status…'
    : isError
      ? 'BIOS status could not be loaded right now, you can check it anytime on the BIOS tab.'
      : required.length > 0
        ? `${present} of ${required.length} required BIOS files present.`
        : 'No BIOS files are marked required yet.'

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        BIOS Files
      </h2>
      <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
        Some emulators, mostly consoles, need a copy of the original system BIOS to run. Peach
        1UP can't provide these for you, they need to come from hardware you own.
      </p>
      <p className="mb-6 text-sm font-medium text-neutral-700 dark:text-neutral-300">{summary}</p>

      <div className="mb-8 flex items-center gap-3">
        <Tooltip content="Uploading and placing BIOS files happens on the Emulators → BIOS tab, not here. You can always come back to it later.">
          <span
            tabIndex={0}
            className="cursor-help text-xs text-neutral-400 underline decoration-dotted dark:text-neutral-500"
          >
            Where do I add these?
          </span>
        </Tooltip>
        <button
          type="button"
          onClick={() => onFinishAndGoTo('/emulators/bios')}
          className="text-sm font-medium text-[#ff8a5c] hover:underline"
        >
          Finish setup & go to BIOS →
        </button>
      </div>

      <p className="mb-8 text-xs text-neutral-400 dark:text-neutral-500">
        Want more depth before diving in?{' '}
        <a
          href={`${DOCS_BASE_URL}/docs/user-guide`}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-[#ff8a5c] hover:underline"
        >
          Browse the guides
        </a>
        .
      </p>

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
          className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
        >
          {finishing ? 'Finishing…' : 'Finish'}
        </button>
      </div>
    </section>
  )
}
