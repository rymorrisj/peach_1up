import { useState } from 'react'
import { apiFetch, ApiError } from '@/api/client'
import type { FirstRunStatus } from './types'

interface Step2EmulatorsProps {
  status: FirstRunStatus
  onNext: () => void
}

interface RowState {
  inputPath: string
  available: boolean
  error: string | null
  saving: boolean
}

export default function Step2Emulators({ status, onNext }: Step2EmulatorsProps) {
  const [rows, setRows] = useState<Record<string, RowState>>(() =>
    Object.fromEntries(
      status.emulators.map((e) => [
        e.slug,
        { inputPath: e.path ?? '', available: e.available, error: null, saving: false },
      ]),
    ),
  )

  function updateRow(slug: string, patch: Partial<RowState>) {
    setRows((prev) => ({ ...prev, [slug]: { ...prev[slug], ...patch } }))
  }

  async function handleSave(slug: string) {
    const row = rows[slug]
    if (!row.inputPath.trim()) return

    updateRow(slug, { saving: true, error: null })
    try {
      const result = await apiFetch<{ slug: string; path: string; available: boolean }>(
        '/api/v1/settings/emulator-path',
        { method: 'POST', body: JSON.stringify({ slug, path: row.inputPath.trim() }) },
      )
      updateRow(slug, { available: result.available, saving: false })
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Failed to save path.'
      updateRow(slug, { error: message, saving: false })
    }
  }

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Configure Emulators
      </h2>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        Enter the path to each emulator binary. DOSBox-X is recommended for DOS
        and Windows 3.1. All others are optional.
      </p>

      <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
        {status.emulators.map((emulator) => {
          const row = rows[emulator.slug]
          const inputId = `emulator-path-${emulator.slug}`
          const errorId = `emulator-error-${emulator.slug}`

          return (
            <li key={emulator.slug} className="py-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {emulator.name}
                </span>
                <span className="text-xs text-neutral-400 dark:text-neutral-500">
                  {emulator.required ? 'recommended' : 'optional'}
                </span>
                <span
                  className={
                    row.available
                      ? 'text-sm text-green-600 dark:text-green-400'
                      : 'text-sm text-amber-500 dark:text-amber-400'
                  }
                >
                  <span aria-hidden="true">{row.available ? '✓' : '✗'}</span>
                  <span className="sr-only">{row.available ? 'Available' : 'Not configured'}</span>
                </span>
              </div>

              <div className="flex gap-2">
                <label htmlFor={inputId} className="sr-only">
                  {emulator.name} binary path
                </label>
                <input
                  id={inputId}
                  type="text"
                  value={row.inputPath}
                  onChange={(e) => updateRow(emulator.slug, { inputPath: e.target.value, error: null })}
                  placeholder={`Path to ${emulator.name} binary`}
                  aria-describedby={row.error ? errorId : undefined}
                  aria-invalid={row.error ? true : undefined}
                  className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600"
                />
                <button
                  type="button"
                  onClick={() => handleSave(emulator.slug)}
                  disabled={row.saving || !row.inputPath.trim()}
                  className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-200 disabled:opacity-50 dark:bg-surface-700 dark:text-neutral-300 dark:hover:bg-surface-600"
                >
                  {row.saving ? 'Saving…' : 'Save'}
                </button>
              </div>

              {row.error && (
                <p id={errorId} role="alert" className="mt-1 text-xs text-[#ff6a55]">
                  {row.error}
                </p>
              )}
            </li>
          )
        })}
      </ul>

      <div className="mt-8 flex justify-end">
        <button
          type="button"
          onClick={onNext}
          className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
        >
          Continue
        </button>
      </div>
    </section>
  )
}
