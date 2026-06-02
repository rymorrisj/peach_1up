import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { EmulatorStatusData, BiosRequirement } from '@/pages/FirstRun/types'
import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']
import EmulatorStatus from '@/components/emulators/EmulatorStatus'

// ─── Shared components ────────────────────────────────────────────────────────

export function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
        ok
          ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
          : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
      }`}
    >
      <span aria-hidden="true">{ok ? '✓' : '✗'}</span>
      {label}
    </span>
  )
}

export function GuidanceBlock({ text, url }: { text?: string | null; url?: string | null }) {
  if (!text) return null
  return (
    <p className="text-sm text-neutral-500 dark:text-neutral-400">
      {text}{' '}
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="text-[#ff8a5c] underline hover:opacity-80"
        >
          Download →
        </a>
      )}
    </p>
  )
}

export function ZipCard({ entry }: { entry: CatalogEntry }) {
  return (
    <div className="space-y-2">
      <EmulatorStatus status={entry.is_installed ? 'Detected' : 'Not detected'} />
      {!entry.is_installed && (
        <GuidanceBlock text={entry.guidance_text} url={entry.guidance_url} />
      )}
      {entry.is_installed && entry.install_path && (
        <p className="font-mono text-xs text-neutral-400 dark:text-neutral-500 break-all">
          {entry.install_path}
        </p>
      )}
    </div>
  )
}

export function InstallerCard({ entry }: { entry: CatalogEntry }) {
  const qc = useQueryClient()
  const [isActing, setIsActing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [detected, setDetected] = useState(entry.is_installed)

  const { data: statusData } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', entry.slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulators/${entry.slug}/status`),
    refetchInterval: isActing ? 3000 : false,
    enabled: isActing,
  })

  useEffect(() => {
    if (!statusData) return
    if (statusData.binary_detected) {
      setDetected(true)
      setIsActing(false)
      qc.invalidateQueries({ queryKey: ['emulators-catalog'] })
    }
    if (statusData.status === 'error') {
      setIsActing(false)
      setActionError(statusData.error ?? 'Install failed.')
    }
  }, [statusData, qc])

  async function handleRunInstaller() {
    setIsActing(true)
    setActionError(null)
    try {
      await apiFetch(`/api/v1/emulators/${entry.slug}/install`, { method: 'POST' })
    } catch (err) {
      setIsActing(false)
      setActionError(err instanceof ApiError ? err.detail : 'Failed to launch installer.')
    }
  }

  const installerPresent = entry.installer_present

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <EmulatorStatus status={installerPresent ? 'Installer ready' : 'Installer not placed'} />
        <EmulatorStatus status={detected ? 'Installed' : 'Not installed'} />
        {installerPresent && !detected && (
          <button
            type="button"
            onClick={handleRunInstaller}
            disabled={isActing}
            className="rounded-md bg-[#ff8a5c] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isActing ? 'Running…' : 'Run Installer'}
          </button>
        )}
      </div>
      {!installerPresent && (
        <GuidanceBlock text={entry.guidance_text} url={entry.guidance_url} />
      )}
      {isActing && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Installer launched — complete the setup, then detection updates automatically.
        </p>
      )}
      {detected && entry.install_path && (
        <p className="font-mono text-xs text-neutral-400 dark:text-neutral-500 break-all">
          {entry.install_path}
        </p>
      )}
      {detected && entry.install_scope === 'system' && (
        <a
          href="ms-settings:appsfeatures"
          className="inline-block text-xs text-neutral-400 underline hover:text-neutral-600 dark:hover:text-neutral-300"
        >
          Uninstall via Windows →
        </a>
      )}
      {actionError && (
        <p role="alert" className="text-xs text-[#ff6a55]">
          {actionError}
        </p>
      )}
    </div>
  )
}

export function RomPackCard({ entry }: { entry: CatalogEntry }) {
  const qc = useQueryClient()
  const [isCloning, setIsCloning] = useState(false)
  const [cloneError, setCloneError] = useState<string | null>(null)
  const [present, setPresent] = useState(entry.is_installed)

  const { data: statusData } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', entry.slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulators/${entry.slug}/status`),
    refetchInterval: isCloning ? 5000 : false,
    enabled: isCloning,
  })

  useEffect(() => {
    if (!statusData) return
    if (statusData.status === 'complete') {
      setPresent(true)
      setIsCloning(false)
      qc.invalidateQueries({ queryKey: ['emulators-catalog'] })
    }
    if (statusData.status === 'error') {
      setIsCloning(false)
      setCloneError(statusData.error ?? 'Clone failed.')
    }
  }, [statusData, qc])

  async function handleClone() {
    setIsCloning(true)
    setCloneError(null)
    try {
      await apiFetch(`/api/v1/emulators/${entry.slug}/install`, { method: 'POST' })
    } catch (err) {
      setIsCloning(false)
      setCloneError(err instanceof ApiError ? err.detail : 'Failed to start clone.')
    }
  }

  const gitOk = entry.git_available !== false

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <EmulatorStatus status={present ? 'Present' : 'Missing'} />
        {!present && gitOk && (
          <button
            type="button"
            onClick={handleClone}
            disabled={isCloning}
            className="rounded-md bg-[#ff8a5c] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isCloning ? 'Cloning…' : 'Clone ROM Pack'}
          </button>
        )}
        {!gitOk && (
          <span className="text-xs text-amber-600 dark:text-amber-400">
            git not found on PATH
          </span>
        )}
      </div>
      {!present && (
        <GuidanceBlock text={entry.guidance_text} url={entry.guidance_url} />
      )}
      {isCloning && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Cloning from GitHub — this may take a few minutes.
        </p>
      )}
      {cloneError && (
        <p role="alert" className="text-xs text-[#ff6a55]">
          {cloneError}
        </p>
      )}
    </div>
  )
}

export function BiosCard({ bios }: { bios: BiosRequirement }) {
  return (
    <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-neutral-900 dark:text-neutral-100">{bios.name}</h3>
          <p className="font-mono text-xs text-neutral-400 dark:text-neutral-500">{bios.bios_path}/</p>
        </div>
        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
            bios.is_present
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
          }`}
        >
          {bios.is_present ? '✓ Present' : '✗ Missing'}
        </span>
      </div>
      {!bios.is_present && (
        <GuidanceBlock text={bios.guidance_text} url={bios.guidance_url} />
      )}
    </div>
  )
}
