import { ZipCard, InstallerCard, RomPackCard, BundledCard, GithubReleaseCard } from './EmulatorCards'
import { useAppContext } from '@/context/useAppContext'
import type { components } from '@shared/types'
type CatalogEntry = components['schemas']['CatalogEntryResponse']

export function MergedEmulatorCard({
  entry,
}: {
  entry: CatalogEntry
}) {
  const { state } = useAppContext()
  const hasActiveLaunch = Array.from(state.activeLaunches.values()).some(
    (e) => e.target_type === 'emulator' && e.ended_at === null,
  )

  return (
    <div className="relative rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      {hasActiveLaunch && (
        <span
          className="absolute right-2 top-2 h-2 w-2 rounded-full bg-green-500"
          aria-hidden="true"
        />
      )}
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-neutral-900 dark:text-neutral-100">{entry.name}</h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">{entry.description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={`rounded px-1.5 py-0.5 text-xs ${
              entry.container_enabled
                ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400'
                : 'bg-neutral-100 text-neutral-500 dark:bg-surface-700 dark:text-neutral-400'
            }`}
          >
            {entry.container_enabled ? 'AppContainer' : 'Job Object'}
          </span>
          <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-500 dark:bg-surface-700 dark:text-neutral-400">
            {entry.license}
          </span>
        </div>
      </div>

      {entry.install_type === 'zip' && <ZipCard entry={entry} />}
      {entry.install_type === 'installer' && <InstallerCard entry={entry} />}
      {entry.install_type === 'rom_pack' && <RomPackCard entry={entry} />}
      {entry.install_type === 'bundled' && <BundledCard entry={entry} />}
      {entry.install_type === 'github_release' && <GithubReleaseCard entry={entry} />}

    </div>
  )
}
