import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { PageHeader, FormField, Button } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'

type LibraryKey = 'images_path' | 'profiles_path' | 'rom_path'

interface PathFieldState {
  value: string
  saving: boolean
  saved: boolean
  error: string | null
}

const PATH_ENTRIES: { key: LibraryKey; settingsKey: string; label: string; hint: string }[] = [
  {
    key: 'images_path',
    settingsKey: 'IMAGES_PATH',
    label: 'Images Path',
    hint: 'Directory where OS images and game media are stored',
  },
  {
    key: 'profiles_path',
    settingsKey: 'PROFILES_PATH',
    label: 'Profiles Path',
    hint: 'Directory where game profiles are saved',
  },
  {
    key: 'rom_path',
    settingsKey: 'ROM_PATH',
    label: 'ROM Path',
    hint: '86Box ROM pack directory — required for accuracy mode',
  },
]

const EMPTY_FIELD: PathFieldState = { value: '', saving: false, saved: false, error: null }

export default function Settings() {
  const { data: settings, isLoading } = useQuery<Record<string, string | null>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch<Record<string, string | null>>('/api/v1/settings'),
  })

  const [fields, setFields] = useState<Record<LibraryKey, PathFieldState>>({
    images_path: EMPTY_FIELD,
    profiles_path: EMPTY_FIELD,
    rom_path: EMPTY_FIELD,
  })
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (!settings || initialized) return
    setFields({
      images_path: { ...EMPTY_FIELD, value: settings['IMAGES_PATH'] ?? '' },
      profiles_path: { ...EMPTY_FIELD, value: settings['PROFILES_PATH'] ?? '' },
      rom_path: { ...EMPTY_FIELD, value: settings['ROM_PATH'] ?? '' },
    })
    setInitialized(true)
  }, [settings, initialized])

  function setField(key: LibraryKey, patch: Partial<PathFieldState>) {
    setFields((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }))
  }

  async function handleSave(key: LibraryKey) {
    const path = fields[key].value.trim()
    if (!path) return
    setField(key, { saving: true, error: null, saved: false })
    try {
      await apiFetch('/api/v1/settings/library-path', {
        method: 'POST',
        body: JSON.stringify({ key, path }),
      })
      setField(key, { saving: false, saved: true })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Failed to save.'
      setField(key, { saving: false, error: msg })
    }
  }

  return (
    <>
      <PageHeader title="Settings" description="Configure library paths and application settings." />

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading settings…" />
          <span aria-hidden="true">Loading settings…</span>
        </div>
      ) : (
        <div className="max-w-xl space-y-8">
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Library Paths
            </h2>
            <div className="mt-4 space-y-5">
              {PATH_ENTRIES.map(({ key, label, hint }) => (
                <FormField
                  key={key}
                  label={label}
                  htmlFor={`path-${key}`}
                  hint={hint}
                  error={fields[key].error ?? undefined}
                >
                  <div className="mt-1 flex gap-2">
                    <PathInput
                      id={`path-${key}`}
                      mode="folder"
                      value={fields[key].value}
                      onChange={(v) => setField(key, { value: v, saved: false })}
                      placeholder={`/path/to/${key.replace('_path', '').replace('_', '-')}`}
                      hasError={!!fields[key].error}
                      className="flex-1 min-w-0"
                    />
                    <Button
                      variant="secondary"
                      onClick={() => handleSave(key)}
                      disabled={!fields[key].value.trim() || fields[key].saving}
                      loading={fields[key].saving}
                    >
                      {fields[key].saved ? 'Saved ✓' : 'Save'}
                    </Button>
                  </div>
                </FormField>
              ))}
            </div>
          </section>

        </div>
      )}
    </>
  )
}
