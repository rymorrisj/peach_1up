import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { Button } from '@/ui'
import { cn } from '@/lib/utils'
import type { CatalogEntry, BiosRequirement } from '@/pages/FirstRun/types'
import { MergedEmulatorCard } from './components/MergedEmulatorCard'
import { BiosCard } from './components/EmulatorCards'
import ProfilesTab from './ProfilesTab'

type EmulatorTab = 'emulators' | 'roms-bios' | 'profiles'

const EMULATOR_TABS: { id: EmulatorTab; label: string }[] = [
  { id: 'emulators', label: 'Emulators' },
  { id: 'roms-bios', label: 'ROM Packs & BIOS' },
  { id: 'profiles', label: 'Profiles' },
]

export default function Emulators() {
  const queryClient = useQueryClient()

  const [activeTab, setActiveTab] = useState<EmulatorTab>('emulators')
  const [installAllRunning, setInstallAllRunning] = useState(false)

  const { data: catalog, isLoading: catalogLoading } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulators'),
    staleTime: 10_000,
  })

  const { data: biosRequirements } = useQuery<BiosRequirement[]>({
    queryKey: ['bios-requirements'],
    queryFn: () => apiFetch<BiosRequirement[]>('/api/v1/bios'),
    staleTime: 10_000,
  })

  const emulatorEntries = (catalog ?? []).filter((e) => e.install_type !== 'rom_pack')
  const romPackEntries = (catalog ?? []).filter((e) => e.install_type === 'rom_pack')

  async function handleInstallAll() {
    if (!catalog) return
    setInstallAllRunning(true)
    const uninstalled = catalog.filter((e) => !e.is_installed)
    for (const entry of uninstalled) {
      try {
        await apiFetch(`/api/v1/emulators/${entry.slug}/install`, { method: 'POST' })
      } catch {
        // Continue with remaining entries
      }
    }
    await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
    setInstallAllRunning(false)
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
          Emulators
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Manage emulators, ROM packs, and launch profiles.
        </p>
      </div>

      {/* ── Tab bar ── */}
      <div className="mb-6 flex border-b border-neutral-200 dark:border-neutral-800">
        {EMULATOR_TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              activeTab === id
                ? 'border-[#ff8a5c] text-[#ff8a5c]'
                : 'border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Emulators tab ── */}
      {activeTab === 'emulators' && (
        <>
          <div className="mb-4 flex flex-wrap justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleInstallAll}
              loading={installAllRunning}
              disabled={installAllRunning || catalogLoading}
            >
              Install All
            </Button>
          </div>
          {catalogLoading && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading…</p>
          )}
          {emulatorEntries.length > 0 && (
            <div className="space-y-3">
              {emulatorEntries.map((entry) => (
                <MergedEmulatorCard
                  key={entry.slug}
                  entry={entry}
                  onCatalogRefresh={() =>
                    queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
                  }
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── ROM Packs & BIOS tab ── */}
      {activeTab === 'roms-bios' && (
        <>
          {romPackEntries.length > 0 && (
            <section aria-labelledby="rompacks-heading" className="mb-10">
              <h2
                id="rompacks-heading"
                className="mb-4 text-base font-semibold text-neutral-700 dark:text-neutral-300"
              >
                ROM Packs
              </h2>
              <div className="space-y-3">
                {romPackEntries.map((entry) => (
                  <MergedEmulatorCard
                    key={entry.slug}
                    entry={entry}
                    onCatalogRefresh={() =>
                      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
                    }
                  />
                ))}
              </div>
            </section>
          )}
          {biosRequirements && biosRequirements.length > 0 && (
            <section aria-labelledby="bios-heading">
              <h2
                id="bios-heading"
                className="mb-2 text-base font-semibold text-neutral-700 dark:text-neutral-300"
              >
                BIOS Files
              </h2>
              <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
                Required firmware assets for console emulators. You are responsible for sourcing
                files you own.
              </p>
              <div className="space-y-3">
                {biosRequirements.map((bios) => (
                  <BiosCard key={bios.slug} bios={bios} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {/* ── Profiles tab ── */}
      {activeTab === 'profiles' && <ProfilesTab />}
    </div>
  )
}
