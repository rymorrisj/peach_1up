import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiFetch, ApiError } from '@/api/client';
import TopBar from '@/components/layout/TopBar';
import { useAppContext } from '@/context/useAppContext';
import { EMULATOR_ERA_MAP, ERA_COLOR } from '@/types/era';
import { useToast } from '@/ui/ToastProvider';
import type { components } from '@shared/types';
type CatalogEntry = components['schemas']['CatalogEntryResponse'];
type LaunchHistory = components['schemas']['LaunchHistoryRead'];

function initials(name: string) {
  return name.slice(0, 2).toUpperCase();
}

function EmulatorCard({
  entry,
  isRunning,
  onClick,
  onDelete,
}: {
  entry: CatalogEntry;
  isRunning: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  const eras = EMULATOR_ERA_MAP[entry.slug] ?? [];
  const isReady = entry.is_installed && entry.install_path;

  return (
    <div
      className="rounded-lg w-full"
      style={{
        background: 'rgb(var(--surface-1))',
        border: '1px solid rgb(var(--border))',
      }}
    >
      {/* Main content, click navigates to detail */}
      <div
        className="p-[18px] cursor-pointer transition-colors duration-[120ms]"
        onClick={onClick}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.background = 'rgb(var(--surface-2))';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLDivElement).style.background = 'transparent';
        }}
      >
        <div className="flex items-start gap-3.5">
          <div
            className="flex shrink-0 items-center justify-center rounded-xl"
            style={{
              width: 52,
              height: 52,
              background: 'rgb(var(--surface-2))',
              border: '1px solid rgb(var(--border-strong))',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: '1.25rem',
              color: 'rgb(var(--peach-300))',
            }}
          >
            {initials(entry.name)}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <span
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 600,
                  fontSize: '1.125rem',
                  lineHeight: 1,
                  color: 'rgb(var(--fg-1))',
                }}
              >
                {entry.name}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.75rem',
                  color: 'rgb(var(--fg-3))',
                }}
              >
                {entry.version}
              </span>
              <span style={{ flex: 1 }} />
              {isRunning && (
                <span
                  className="inline-flex items-center gap-1.5 rounded-full"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.6875rem',
                    fontWeight: 500,
                    padding: '2px 8px',
                    background: 'rgb(var(--success) / 0.12)',
                    color: 'rgb(var(--success))',
                    border: '1px solid rgb(var(--success) / 0.3)',
                  }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{
                      background: 'rgb(var(--success))',
                      animation: 'dot-pulse 1.4s ease-in-out infinite',
                    }}
                    aria-hidden="true"
                  />
                  Running
                </span>
              )}
              <span
                className="inline-flex items-center gap-1.5"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6875rem',
                  fontWeight: 500,
                  color: isReady ? 'rgb(var(--success))' : 'rgb(var(--error))',
                }}
              >
                <span
                  className="rounded-full inline-block"
                  style={{
                    width: 6,
                    height: 6,
                    background: isReady ? 'rgb(var(--success))' : 'rgb(var(--error))',
                  }}
                />
                {isReady ? 'Ready' : 'Not installed'}
              </span>
            </div>

            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: '0.8125rem',
                lineHeight: 1.4,
                color: 'rgb(var(--fg-2))',
                marginBottom: 12,
              }}
            >
              {entry.description}
            </div>

            {eras.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3.5">
                {eras.map((era) => (
                  <span
                    key={era}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      fontSize: '0.6875rem',
                      letterSpacing: '0.08em',
                      padding: '4px 6px',
                      borderRadius: 'var(--r-1)',
                      border: `1px solid ${ERA_COLOR[era] ?? 'rgb(var(--border))'}`,
                      color: ERA_COLOR[era] ?? 'rgb(var(--fg-3))',
                      display: 'inline-block',
                    }}
                  >
                    {era}
                  </span>
                ))}
              </div>
            )}

            <div
              className="flex gap-[18px] pt-3"
              style={{
                borderTop: '1px solid rgb(var(--border))',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem',
                fontWeight: 500,
                color: 'rgb(var(--fg-3))',
              }}
            >
              <span>
                <strong style={{ color: 'rgb(var(--fg-1))', marginRight: 4 }}>
                  {entry.install_type === 'rom_pack' ? '—' : entry.is_installed ? '✓' : '○'}
                </strong>
                {entry.install_type}
              </span>
              {entry.license && (
                <span>
                  <strong style={{ color: 'rgb(var(--fg-1))', marginRight: 4 }}>
                    {entry.license}
                  </strong>
                  license
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Action bar */}
      <div
        className="px-[18px] py-2.5 flex gap-2 justify-end items-center"
        style={{ borderTop: '1px solid rgb(var(--border))' }}
      >
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          style={{
            border: '1px solid rgb(var(--error))',
            fontFamily: 'var(--font-display)',
            fontSize: '0.75rem',
            fontWeight: 500,
            padding: '5px 10px',
            borderRadius: 'var(--r-2)',
            cursor: 'pointer',
            background: 'transparent',
            color: 'rgb(var(--error))',
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

export default function Emulators() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { state } = useAppContext();

  const { data: catalog = [], isLoading } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulator-items'),
    staleTime: 10_000,
  });

  // Same queryKey/queryFn as TopBar's and EmulatorDetail's launches query, so
  // all three share one cache entry and one poll instead of issuing duplicate
  // requests.
  const { data: launches = [] } = useQuery<LaunchHistory[]>({
    queryKey: ['launches'],
    queryFn: () => apiFetch<LaunchHistory[]>('/api/v1/launches'),
    enabled: !!state.activeUser,
    refetchInterval: (query) => {
      const data = query.state.data ?? [];
      return data.some((l) => l.ended_at === null) ? 5000 : false;
    },
    refetchOnWindowFocus: false,
  });

  const runningSlugs = new Set<string>(
    launches.filter((l) => l.ended_at === null).map((l) => l.emulator_slug),
  );

  const emulatorEntries = catalog.filter((e) => e.install_type !== 'rom_pack');
  const installedCount = emulatorEntries.filter((e) => e.is_installed).length;

  async function handleDelete(entry: CatalogEntry) {
    if (
      !window.confirm(
        `Remove "${entry.name}"? This unregisters the binary but does not delete files.`,
      )
    )
      return;
    try {
      const { token } = await apiFetch<{ token: string }>(
        `/api/v1/emulator-items/${entry.slug}/confirm-token`,
      );
      await apiFetch(`/api/v1/emulator-items/${entry.slug}`, {
        method: 'DELETE',
        body: JSON.stringify({ confirmation_token: token }),
      });
      await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Remove failed.', 'error');
    }
  }

  async function handleAutoDetect() {
    await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          onClick={handleAutoDetect}
          className="ml-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-[120ms]"
          style={{
            fontFamily: 'var(--font-display)',
            background: 'rgb(var(--surface-2))',
            border: '1px solid rgb(var(--border))',
            color: 'rgb(var(--fg-1))',
            cursor: 'pointer',
          }}
        >
          Auto-detect
        </button>
      </TopBar>

      <div className="p-6">
        <div className="mb-3 flex items-baseline gap-2.5">
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              fontSize: '1.125rem',
              letterSpacing: '-0.01em',
              margin: 0,
              color: 'rgb(var(--fg-1))',
            }}
          >
            Installed backends
          </h2>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.8125rem',
              color: 'rgb(var(--fg-3))',
            }}
          >
            {installedCount} of {emulatorEntries.length} ready
          </span>
        </div>

        {isLoading ? (
          <div
            style={{
              color: 'rgb(var(--fg-3))',
              fontFamily: 'var(--font-display)',
              fontSize: '0.875rem',
            }}
          >
            Loading…
          </div>
        ) : emulatorEntries.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center text-sm"
            style={{
              border: '1px dashed rgb(var(--border-strong))',
              color: 'rgb(var(--fg-3))',
              backgroundImage:
                'repeating-linear-gradient(0deg, transparent 0 11px, rgb(var(--peach-500) / 0.04) 11px 12px), repeating-linear-gradient(90deg, transparent 0 11px, rgb(var(--peach-500) / 0.04) 11px 12px)',
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
                isRunning={runningSlugs.has(entry.slug)}
                onClick={() => navigate(`/emulators/${entry.slug}`)}
                onDelete={() => handleDelete(entry)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
