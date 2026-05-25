import { useState } from 'react'
import { apiFetch, ApiError } from '@/api/client'
import type { FirstRunStatus } from './types'

interface Step3PathsProps {
  status: FirstRunStatus
  onNext: () => void
}

type LibraryKey = 'library_path' | 'profiles_path' | 'roms_path'

interface PathConfig {
  label: string
  key: LibraryKey
  required: boolean
  description: string
}

const PATH_ROWS: PathConfig[] = [
  {
    label: 'Library folder',
    key: 'library_path',
    required: true,
    description: 'Root folder for the Peach 1UP library',
  },
  {
    label: 'Profiles folder',
    key: 'profiles_path',
    required: true,
    description: 'Where game profiles are saved',
  },
  {
    label: 'ROM pack folder',
    key: 'roms_path',
    required: false,
    description: 'Required for 86Box accuracy mode only',
  },
]

interface RowState {
  inputPath: string
  saved: boolean
  error: string | null
  saving: boolean
}

export default function Step3Paths({ status, onNext }: Step3PathsProps) {
  const [rows, setRows] = useState<Record<LibraryKey, RowState>>({
    library_path: {
      inputPath: status.paths.library_path ?? '',
      saved: !!status.paths.library_path,
      error: null,
      saving: false,
    },
    profiles_path: {
      inputPath: status.paths.profiles_path ?? '',
      saved: !!status.paths.profiles_path,
      error: null,
      saving: false,
    },
    roms_path: {
      inputPath: status.paths.roms_path ?? '',
      saved: !!status.paths.roms_path,
      error: null,
      saving: false,
    },
  })

  function updateRow(key: LibraryKey, patch: Partial<RowState>) {
    setRows((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }))
  }

  async function handleSave(key: LibraryKey) {
    const row = rows[key]
    if (!row.inputPath.trim()) return

    updateRow(key, { saving: true, error: null })
    try {
      await apiFetch('/api/v1/settings/library-path', {
        method: 'POST',
        body: JSON.stringify({ key, path: row.inputPath.trim() }),
      })
      updateRow(key, { saved: true, saving: false })
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Failed to save path.'
      updateRow(key, { error: message, saving: false, saved: false })
    }
  }

  const canContinue = rows.library_path.saved && rows.profiles_path.saved

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Set Library Paths
      </h2>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        Configure where Peach 1UP stores your library data. Images and Profiles
        are required. ROM pack is optional and only needed for 86Box.
      </p>

      <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
        {PATH_ROWS.map(({ label, key, required, description }) => {
          const row = rows[key]
          const inputId = `path-${key}`
          const errorId = `path-error-${key}`

          return (
            <li key={key} className="py-4">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {label}
                </span>
                {!required && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">optional</span>
                )}
                {row.saved && (
                  <span className="text-xs text-green-600 dark:text-green-400">✓ saved</span>
                )}
              </div>
              <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">{description}</p>

              <div className="flex gap-2">
                <label htmlFor={inputId} className="sr-only">
                  {label}
                </label>
                <input
                  id={inputId}
                  type="text"
                  value={row.inputPath}
                  onChange={(e) =>
                    updateRow(key, { inputPath: e.target.value, error: null, saved: false })
                  }
                  placeholder={`Path to ${label.toLowerCase()}`}
                  aria-describedby={row.error ? errorId : undefined}
                  aria-invalid={row.error ? true : undefined}
                  className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600"
                />
                <button
                  type="button"
                  onClick={() => handleSave(key)}
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
          disabled={!canContinue}
          className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
        >
          Continue
        </button>
      </div>
    </section>
  )
}
