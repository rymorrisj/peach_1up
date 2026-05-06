import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { CatalogEntry, EmulatorInstallStatus } from '@/pages/FirstRun/types'

interface EmulatorRowProps {
  entry: CatalogEntry
}

function EmulatorRow({ entry }: EmulatorRowProps) {
  const [inputPath, setInputPath] = useState(entry.install_path ?? '')
  const [available, setAvailable] = useState(entry.is_installed)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [isInstalling, setIsInstalling] = useState(false)
  const [installError, setInstallError] = useState<string | null>(null)

  const { data: installStatus } = useQuery<EmulatorInstallStatus>({
    queryKey: ['emulator-install-status', entry.slug],
    queryFn: () =>
      apiFetch<EmulatorInstallStatus>(`/api/v1/emulators/${entry.slug}/install/status`),
    refetchInterval: isInstalling ? 2000 : false,
    enabled: isInstalling,
  })

  useEffect(() => {
    if (!installStatus) return
    if (installStatus.status === 'complete') {
      setIsInstalling(false)
      if (installStatus.install_path) {
        setInputPath(installStatus.install_path)
        setAvailable(true)
      }
    }
    if (installStatus.status === 'error') {
      setIsInstalling(false)
      setInstallError(installStatus.error ?? 'Install failed.')
    }
  }, [installStatus])

  async function handleInstall() {
    setIsInstalling(true)
    setInstallError(null)
    try {
      await apiFetch(`/api/v1/emulators/${entry.slug}/install`, { method: 'POST' })
    } catch (err) {
      setIsInstalling(false)
      const message = err instanceof ApiError ? err.detail : 'Failed to start install.'
      setInstallError(message)
    }
  }

  async function handleSave() {
    if (!inputPath.trim()) return
    setSaving(true)
    setSaveError(null)
    try {
      const result = await apiFetch<{ slug: string; path: string; available: boolean }>(
        '/api/v1/settings/emulator-path',
        { method: 'POST', body: JSON.stringify({ slug: entry.slug, path: inputPath.trim() }) },
      )
      setAvailable(result.available)
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Failed to save path.'
      setSaveError(message)
    } finally {
      setSaving(false)
    }
  }

  const inputId = `emulator-path-${entry.slug}`
  const errorId = `emulator-error-${entry.slug}`
  const hasError = saveError !== null || installError !== null

  return (
    <li className="py-4">
      <div className="mb-1 flex items-center gap-2">
        <span className="font-medium text-neutral-900 dark:text-neutral-100">{entry.name}</span>
        <span className="text-xs text-neutral-400 dark:text-neutral-500">{entry.license}</span>
        <span
          className={
            available
              ? 'text-sm text-green-600 dark:text-green-400'
              : 'text-sm text-amber-500 dark:text-amber-400'
          }
        >
          <span aria-hidden="true">{available ? '✓' : '✗'}</span>
          <span className="sr-only">{available ? 'Installed' : 'Not configured'}</span>
        </span>
      </div>
      <p className="mb-2 text-xs text-neutral-400 dark:text-neutral-500">{entry.description}</p>
      {entry.supported_formats && entry.supported_formats.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {entry.supported_formats.map((fmt) => (
            <span
              key={fmt}
              className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-500 dark:bg-surface-700 dark:text-neutral-400"
            >
              {fmt}
            </span>
          ))}
        </div>
      )}

      {entry.install_note ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {entry.install_note}{' '}
          <a
            href="https://www.virtualbox.org"
            target="_blank"
            rel="noreferrer"
            className="text-[#ff8a5c] underline hover:opacity-80"
          >
            virtualbox.org
          </a>
        </p>
      ) : (
        <div className="flex gap-2">
          <label htmlFor={inputId} className="sr-only">
            {entry.name} binary path
          </label>
          <input
            id={inputId}
            type="text"
            value={inputPath}
            onChange={(e) => {
              setInputPath(e.target.value)
              setSaveError(null)
            }}
            placeholder={`Path to ${entry.name} binary`}
            aria-describedby={hasError ? errorId : undefined}
            aria-invalid={hasError ? true : undefined}
            className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600"
          />
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !inputPath.trim()}
            className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-200 disabled:opacity-50 dark:bg-surface-700 dark:text-neutral-300 dark:hover:bg-surface-600"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          {entry.is_placeholder ? (
            <span className="rounded-md bg-neutral-200 px-4 py-2 text-sm font-medium text-neutral-500 dark:bg-surface-700 dark:text-neutral-500">
              Not yet available
            </span>
          ) : (
            <button
              type="button"
              onClick={handleInstall}
              disabled={isInstalling}
              className="rounded-md bg-[#ff8a5c] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {isInstalling ? 'Installing…' : 'Install'}
            </button>
          )}
        </div>
      )}

      {hasError && (
        <p id={errorId} role="alert" className="mt-1 text-xs text-[#ff6a55]">
          {saveError ?? installError}
        </p>
      )}
    </li>
  )
}

export default function EmulatorsSettings() {
  const { data: catalog, isLoading } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulators'),
  })

  return (
    <>
      <h1 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Emulators
      </h1>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        Install or configure each emulator. All emulators are optional — install only what you
        need for your library.
      </p>

      {isLoading ? (
        <p className="text-sm text-neutral-400">Loading…</p>
      ) : (
        <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {(catalog ?? []).map((entry) => (
            <EmulatorRow key={entry.slug} entry={entry} />
          ))}
        </ul>
      )}
    </>
  )
}
