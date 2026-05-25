import { ZipCard, InstallerCard, RomPackCard, VBoxExpertCard } from './EmulatorCards'
import { useAppContext } from '@/context/AppContext'
import type { CatalogEntry } from '@/pages/FirstRun/types'

export function MergedEmulatorCard({
  entry,
  onCatalogRefresh,
}: {
  entry: CatalogEntry
  onCatalogRefresh: () => void
}) {
  const { state } = useAppContext()
  const showExpertCard = entry.slug === 'virtualbox' && entry.is_installed && !entry.expert_mode_set
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
        <span className="shrink-0 rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-500 dark:bg-surface-700 dark:text-neutral-400">
          {entry.license}
        </span>
      </div>

      {entry.install_type === 'zip' && <ZipCard entry={entry} />}
      {entry.install_type === 'installer' && <InstallerCard entry={entry} />}
      {entry.install_type === 'rom_pack' && <RomPackCard entry={entry} />}

      {showExpertCard && <VBoxExpertCard entry={entry} onDone={onCatalogRefresh} />}
    </div>
  )
}
