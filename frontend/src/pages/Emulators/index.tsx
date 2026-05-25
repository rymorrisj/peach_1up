import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import type { CatalogEntry } from '@/pages/FirstRun/types'

const ERA_MAP: Record<string, string[]> = {
  'dosbox-x':   ['DOS', 'WIN31'],
  '86box':       ['WIN95', 'WIN98'],
  'virtualbox':  ['WIN95', 'WIN98', 'WINXP'],
  'duckstation': ['PS1'],
  'pcsx2':       ['PS2'],
  'xemu':        ['XBOX'],
  'flycast':     ['DC'],
  'mesen':       ['NES'],
  'project64':   ['N64'],
  'scummvm':     ['DOS'],
}

const ERA_COLOR: Record<string, string> = {
  DOS:   'var(--era-dos)',
  WIN31: 'var(--era-win31)',
  WIN95: 'var(--era-win95)',
  WIN98: 'var(--era-win98)',
  WINXP: 'var(--era-winxp)',
  PS1:   '#a9a0d6',
  PS2:   '#6090d0',
  XBOX:  '#6db36d',
  DC:    '#d0a060',
  NES:   '#d06060',
  N64:   '#60a0d0',
}

function initials(name: string) {
  return name.slice(0, 2).toUpperCase()
}

function EmulatorCard({ entry, onClick }: { entry: CatalogEntry; onClick: () => void }) {
  const eras = ERA_MAP[entry.slug] ?? []
  const isReady = entry.is_installed && entry.install_path

  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg p-[18px] text-left transition-colors duration-[120ms] w-full"
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border)',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--surface-2)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'var(--surface-1)'
      }}
    >
      <div className="flex items-start gap-3.5">
        {/* Avatar */}
        <div
          className="flex shrink-0 items-center justify-center rounded-xl"
          style={{
            width: 52,
            height: 52,
            background: 'var(--surface-2)',
            border: '1px solid var(--border-strong)',
            fontFamily: 'var(--font-mono)',
            fontWeight: 700,
            fontSize: 20,
            color: 'var(--peach-300)',
          }}
        >
          {initials(entry.name)}
        </div>

        <div className="flex-1 min-w-0">
          {/* Name row */}
          <div className="flex items-center gap-2.5 mb-1.5">
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, lineHeight: 1, color: 'var(--fg-1)' }}>
              {entry.name}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
              {entry.version}
            </span>
            <span style={{ flex: 1 }} />
            <span
              className="inline-flex items-center gap-1.5"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                fontWeight: 500,
                color: isReady ? 'var(--success)' : 'var(--error)',
              }}
            >
              <span
                className="rounded-full inline-block"
                style={{
                  width: 6,
                  height: 6,
                  background: isReady ? 'var(--success)' : 'var(--error)',
                }}
              />
              {isReady ? 'Ready' : 'Not installed'}
            </span>
          </div>

          {/* Description */}
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, lineHeight: 1.4, color: 'var(--fg-2)', marginBottom: 12 }}>
            {entry.description}
          </div>

          {/* Era chips */}
          {eras.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3.5">
              {eras.map((era) => (
                <span
                  key={era}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    fontSize: 11,
                    letterSpacing: '0.08em',
                    padding: '4px 6px',
                    borderRadius: 'var(--r-1)',
                    border: `1px solid ${ERA_COLOR[era] ?? 'var(--border)'}`,
                    color: ERA_COLOR[era] ?? 'var(--fg-3)',
                    display: 'inline-block',
                  }}
                >
                  {era}
                </span>
              ))}
            </div>
          )}

          {/* Stats row */}
          <div
            className="flex gap-[18px] pt-3"
            style={{
              borderTop: '1px solid var(--border)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--fg-3)',
            }}
          >
            <span>
              <strong style={{ color: 'var(--fg-1)', marginRight: 4 }}>
                {entry.install_type === 'rom_pack' ? '—' : (entry.is_installed ? '✓' : '○')}
              </strong>
              {entry.install_type}
            </span>
            {entry.license && (
              <span>
                <strong style={{ color: 'var(--fg-1)', marginRight: 4 }}>{entry.license}</strong>
                license
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

export default function Emulators() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: catalog = [], isLoading } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulators'),
    staleTime: 10_000,
  })

  const emulatorEntries = catalog.filter((e) => e.install_type !== 'rom_pack')
  const installedCount = emulatorEntries.filter((e) => e.is_installed).length

  async function handleAutoDetect() {
    await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] })
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Emulators">
        <button
          type="button"
          onClick={handleAutoDetect}
          className="ml-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-[120ms]"
          style={{
            fontFamily: 'var(--font-display)',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            color: 'var(--fg-1)',
            cursor: 'pointer',
          }}
        >
          Auto-detect
        </button>
      </TopBar>

      <div className="p-6">
        <div className="mb-3 flex items-baseline gap-2.5">
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 18, letterSpacing: '-0.01em', margin: 0, color: 'var(--fg-1)' }}>
            Installed backends
          </h2>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-3)' }}>
            {installedCount} of {emulatorEntries.length} ready
          </span>
        </div>

        {isLoading ? (
          <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-display)', fontSize: 14 }}>Loading…</div>
        ) : emulatorEntries.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center text-sm"
            style={{
              border: '1px dashed var(--border-strong)',
              color: 'var(--fg-3)',
              backgroundImage:
                'repeating-linear-gradient(0deg, transparent 0 11px, rgb(255 138 92 / 0.04) 11px 12px), repeating-linear-gradient(90deg, transparent 0 11px, rgb(255 138 92 / 0.04) 11px 12px)',
            }}
          >
            No emulators found. Check your configuration.
          </div>
        ) : (
          <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 1fr' }}>
            {emulatorEntries.map((entry) => (
              <EmulatorCard
                key={entry.slug}
                entry={entry}
                onClick={() => navigate(`/emulators/${entry.slug}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
