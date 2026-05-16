import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import type { FirstRunStatus, CatalogEntry, EmulatorStatusData, BiosRequirement } from './types'

interface Step2EmulatorsProps {
  status: FirstRunStatus
  onNext: () => void
}

function GuidanceLink({ text, url }: { text?: string; url?: string }) {
  if (!text) return null
  return (
    <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
      {text}{' '}
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="text-[#ff8a5c] underline hover:opacity-80"
        >
          Download
        </a>
      )}
    </p>
  )
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={ok ? 'text-green-600 dark:text-green-400' : 'text-amber-500 dark:text-amber-400'}
      aria-hidden="true"
    >
      {ok ? '✓' : '✗'}
    </span>
  )
}

function ZipRow({ entry, savedPath }: { entry: CatalogEntry; savedPath: string }) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <StatusDot ok={entry.is_installed || !!savedPath} />
        <span className="text-sm text-neutral-600 dark:text-neutral-400">
          {entry.is_installed ? 'Detected' : savedPath ? 'Path saved' : 'Not detected'}
        </span>
      </div>
      {!entry.is_installed && !savedPath && (
        <GuidanceLink text={entry.guidance_text} url={entry.guidance_url} />
      )}
    </div>
  )
}

function InstallerRow({ entry }: { entry: CatalogEntry }) {
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
    }
    if (statusData.status === 'error') {
      setIsActing(false)
      setActionError(statusData.error ?? 'Install failed.')
    }
  }, [statusData])

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
    <div>
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 text-sm">
          <StatusDot ok={installerPresent} />
          <span className="text-neutral-500 dark:text-neutral-400">
            {installerPresent ? 'Installer ready' : 'Installer not placed'}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-sm">
          <StatusDot ok={detected} />
          <span className="text-neutral-500 dark:text-neutral-400">
            {detected ? 'Installed' : isActing ? 'Waiting for install…' : 'Not installed'}
          </span>
        </div>
        {installerPresent && !detected && (
          <button
            type="button"
            onClick={handleRunInstaller}
            disabled={isActing}
            className="rounded-md bg-[#ff8a5c] px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isActing ? 'Running…' : 'Run Installer'}
          </button>
        )}
      </div>
      {!installerPresent && (
        <GuidanceLink text={entry.guidance_text} url={entry.guidance_url} />
      )}
      {actionError && (
        <p role="alert" className="mt-1 text-xs text-[#ff6a55]">
          {actionError}
        </p>
      )}
    </div>
  )
}

function RomPackRow({ entry }: { entry: CatalogEntry }) {
  const [isCloning, setIsCloning] = useState(false)
  const [cloneError, setCloneError] = useState<string | null>(null)
  const [cloned, setCloned] = useState(entry.is_installed)

  const { data: statusData } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', entry.slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulators/${entry.slug}/status`),
    refetchInterval: isCloning ? 4000 : false,
    enabled: isCloning,
  })

  useEffect(() => {
    if (!statusData) return
    if (statusData.status === 'complete') {
      setCloned(true)
      setIsCloning(false)
    }
    if (statusData.status === 'error') {
      setIsCloning(false)
      setCloneError(statusData.error ?? 'Clone failed.')
    }
  }, [statusData])

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
    <div>
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 text-sm">
          <StatusDot ok={cloned} />
          <span className="text-neutral-500 dark:text-neutral-400">
            {cloned ? 'ROM pack present' : 'ROM pack missing'}
          </span>
        </div>
        {!cloned && gitOk && (
          <button
            type="button"
            onClick={handleClone}
            disabled={isCloning}
            className="rounded-md bg-[#ff8a5c] px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isCloning ? 'Cloning…' : 'Clone ROM Pack'}
          </button>
        )}
        {!cloned && !gitOk && (
          <span className="text-sm text-amber-500 dark:text-amber-400">git not found on PATH</span>
        )}
      </div>
      {!cloned && (
        <GuidanceLink text={entry.guidance_text} url={entry.guidance_url} />
      )}
      {cloneError && (
        <p role="alert" className="mt-1 text-xs text-[#ff6a55]">
          {cloneError}
        </p>
      )}
    </div>
  )
}

function EmulatorRow({
  slug,
  name,
  required,
  savedPath,
  catalogEntry,
}: {
  slug: string
  name: string
  required: boolean
  savedPath: string
  catalogEntry: CatalogEntry | undefined
}) {
  const [inputPath, setInputPath] = useState(savedPath)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (catalogEntry?.is_installed && catalogEntry.install_path && !inputPath) {
      setInputPath(catalogEntry.install_path)
    }
  }, [catalogEntry?.is_installed, catalogEntry?.install_path])

  async function handleSave() {
    if (!inputPath.trim()) return
    setSaving(true)
    setSaveError(null)
    try {
      await apiFetch<{ slug: string; path: string; available: boolean }>(
        '/api/v1/settings/emulator-path',
        { method: 'POST', body: JSON.stringify({ slug, path: inputPath.trim() }) },
      )
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Failed to save path.')
    } finally {
      setSaving(false)
    }
  }

  const installType = catalogEntry?.install_type ?? 'zip'
  const inputId = `emulator-path-${slug}`

  return (
    <li className="py-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-medium text-neutral-900 dark:text-neutral-100">{name}</span>
        <span className="text-xs text-neutral-400 dark:text-neutral-500">
          {required ? 'recommended' : 'optional'}
        </span>
      </div>

      {catalogEntry && (
        <div className="mb-3">
          {installType === 'zip' && (
            <ZipRow entry={catalogEntry} savedPath={savedPath} />
          )}
          {installType === 'installer' && (
            <InstallerRow entry={catalogEntry} />
          )}
          {installType === 'rom_pack' && (
            <RomPackRow entry={catalogEntry} />
          )}
        </div>
      )}

      {installType !== 'rom_pack' && (
        <div className="flex gap-2">
          <label htmlFor={inputId} className="sr-only">
            {name} binary path override
          </label>
          <input
            id={inputId}
            type="text"
            value={inputPath}
            onChange={(e) => {
              setInputPath(e.target.value)
              setSaveError(null)
            }}
            placeholder={`Custom path to ${name} binary (optional)`}
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
        </div>
      )}

      {saveError && (
        <p role="alert" className="mt-1 text-xs text-[#ff6a55]">
          {saveError}
        </p>
      )}
    </li>
  )
}

function BiosCard({ bios }: { bios: BiosRequirement }) {
  return (
    <li className="py-4">
      <div className="mb-1 flex items-center gap-2">
        <span className="font-medium text-neutral-900 dark:text-neutral-100">{bios.name}</span>
        <span className="text-xs text-neutral-400 dark:text-neutral-500">required asset</span>
        <StatusDot ok={bios.is_present} />
      </div>
      <p className="text-xs font-mono text-neutral-400 dark:text-neutral-500 mb-1">
        {bios.bios_path}/
      </p>
      {!bios.is_present && (
        <GuidanceLink text={bios.guidance_text} url={bios.guidance_url} />
      )}
      {bios.is_present && (
        <p className="text-sm text-green-600 dark:text-green-400">Files detected</p>
      )}
    </li>
  )
}

export default function Step2Emulators({ status, onNext }: Step2EmulatorsProps) {
  const { data: catalog } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulators'),
  })

  const { data: biosRequirements } = useQuery<BiosRequirement[]>({
    queryKey: ['bios-requirements'],
    queryFn: () => apiFetch<BiosRequirement[]>('/api/v1/bios'),
  })

  const catalogBySlug = Object.fromEntries((catalog ?? []).map((e) => [e.slug, e]))
  const romPackEntry = catalogBySlug['86box-roms']

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Configure Emulators
      </h2>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        Install or locate each emulator. All items are optional — you can set them up later from
        the Emulators page.
      </p>

      <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
        {status.emulators.map((emulator) => (
          <EmulatorRow
            key={emulator.slug}
            slug={emulator.slug}
            name={emulator.name}
            required={emulator.required}
            savedPath={emulator.path ?? catalogBySlug[emulator.slug]?.install_path ?? ''}
            catalogEntry={catalogBySlug[emulator.slug]}
          />
        ))}

        {romPackEntry && (
          <li className="py-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-medium text-neutral-900 dark:text-neutral-100">
                {romPackEntry.name}
              </span>
              <span className="text-xs text-neutral-400 dark:text-neutral-500">optional</span>
            </div>
            <RomPackRow entry={romPackEntry} />
          </li>
        )}
      </ul>

      {biosRequirements && biosRequirements.length > 0 && (
        <>
          <h3 className="mt-8 mb-2 text-base font-semibold text-neutral-700 dark:text-neutral-300">
            Required BIOS Files
          </h3>
          <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
            These assets are needed for specific emulators. Advisory only — you can add them later.
          </p>
          <ul role="list" className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {biosRequirements.map((bios) => (
              <BiosCard key={bios.slug} bios={bios} />
            ))}
          </ul>
        </>
      )}

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
