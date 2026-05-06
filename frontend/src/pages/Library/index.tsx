import { useState } from 'react'
import EraSelector, { type EraValue } from '@/components/common/EraSelector'

export default function Library() {
  const [selectedEra, setSelectedEra] = useState<EraValue | null>(null)

  return (
    <>
      <h1 className="mb-6 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Library
      </h1>

      <div className="max-w-xl">
        <h2 className="mb-1 text-base font-medium text-neutral-900 dark:text-neutral-100">
          Select a platform
        </h2>
        <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
          Choose the platform your media targets. Peach 1UP selects the correct emulator
          automatically.
        </p>

        <EraSelector value={selectedEra} onChange={setSelectedEra} />

        {selectedEra && (
          <div className="mt-6">
            <button
              type="button"
              className="rounded-md bg-[#ff8a5c] px-5 py-2 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
            >
              Continue with {selectedEra.toUpperCase()}
            </button>
          </div>
        )}
      </div>
    </>
  )
}
