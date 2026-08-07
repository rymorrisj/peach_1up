import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import TopBar from '@/components/layout/TopBar';
import { ERA_COLOR, ERA_LABEL } from '@/types/era';
import type { components } from '@shared/types';

type Platform = components['schemas']['EnvironmentItemRead'];

interface EraBreakdown {
  era: string;
  label: string;
  size_bytes: number;
  count: number;
}

interface StorageCategory {
  key: string;
  label: string;
  size_bytes: number;
  breakdown: EraBreakdown[];
  unsized_count?: number;
}

interface StorageFootprint {
  categories: StorageCategory[];
  total_bytes: number;
  last_updated: string;
}

interface HealthSummary {
  environments: { total: number; present: number };
  library: { total: number };
  drives: { total: number };
  extensions: { total: number };
  emulators: { total: number; installed: number };
  bios: { total: number; present: number };
  rom_packs: { total: number; installed: number };
}

function formatBytes(n: number) {
  if (n >= 1_073_741_824) return `${(n / 1_073_741_824).toFixed(1)} GB`;
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(0)} MB`;
  if (n >= 1_024) return `${(n / 1_024).toFixed(0)} KB`;
  return `${n} B`;
}

// Live presence check (compute_environment_presence, computed fresh on
// every read, nothing persisted or cached), replaces the old stale
// isHealthy(status), which treated the never-updated "unknown" default as
// healthy and so never actually gated anything.
export function isHealthy(p: Platform) {
  return p.is_present;
}

function StatusDot({ healthy }: { healthy: boolean }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{
        width: 8,
        height: 8,
        background: healthy ? 'rgb(var(--success))' : 'rgb(var(--error))',
        boxShadow: healthy
          ? '0 0 12px rgb(var(--success) / 0.5)'
          : '0 0 12px rgb(var(--error) / 0.5)',
      }}
    />
  );
}

function EraChip({ era }: { era: string }) {
  const eraKey = ERA_LABEL[era] ?? era.toUpperCase();
  const color = ERA_COLOR[eraKey] ?? 'rgb(var(--fg-3))';
  const label = eraKey;
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        fontSize: '0.6875rem',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        padding: '4px 6px',
        borderRadius: 'var(--r-1)',
        border: `1px solid ${color}`,
        color,
        display: 'inline-block',
      }}
    >
      {label}
    </span>
  );
}

const CAT_COLORS: Record<string, string> = {
  emulators: '#6a9fd8',
  library_media: 'rgb(var(--peach-500))',
  library_system: '#8f72c8',
  drive_images: '#d87fb0',
  environments: '#5ab87a',
  external: 'rgb(var(--fg-3))',
  database: '#c8a84a',
  logs: 'var(--fg-4)',
};

// A 403 means the user lacks the platforms permission, stop retrying and
// polling immediately instead of burning the normal retry count. Any other
// error (network, 500, etc.) keeps the default retry behavior.
function retryUnlessForbidden(failureCount: number, error: unknown) {
  if (error instanceof ApiError && error.status === 403) return false;
  return failureCount < 1;
}

export default function Health() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [rescanning, setRescanning] = useState(false);
  // Checked once per page load: as soon as any Platform Health query comes
  // back 403, stop querying/polling for the rest of this page's lifetime
  // and show a terminal no-permission state.
  const [permissionDenied, setPermissionDenied] = useState(false);

  const {
    data: platforms = [],
    isLoading,
    error: platformsError,
  } = useQuery<Platform[]>({
    queryKey: ['platforms'],
    queryFn: () => apiFetch<Platform[]>('/api/v1/environment-items'),
    enabled: !permissionDenied,
    retry: retryUnlessForbidden,
  });

  const {
    data: storageFootprint,
    isLoading: storageLoading,
    refetch: refetchStorage,
    error: storageError,
  } = useQuery<StorageFootprint>({
    queryKey: ['health-storage'],
    queryFn: () => apiFetch<StorageFootprint>('/api/v1/health/storage'),
    enabled: !permissionDenied,
    retry: retryUnlessForbidden,
  });

  const {
    data: summary,
    isError: summaryError,
    isLoading: summaryLoading,
    error: summaryQueryError,
  } = useQuery<HealthSummary>({
    queryKey: ['platforms-health-summary'],
    queryFn: () => apiFetch<HealthSummary>('/api/v1/health/summary'),
    enabled: !permissionDenied,
    retry: retryUnlessForbidden,
  });

  useEffect(() => {
    const errors = [platformsError, storageError, summaryQueryError];
    if (errors.some((e) => e instanceof ApiError && e.status === 403)) {
      setPermissionDenied(true);
    }
  }, [platformsError, storageError, summaryQueryError]);

  const userPlatforms = platforms;
  const healthy = userPlatforms.filter(isHealthy);
  const degraded = userPlatforms.filter((p) => !isHealthy(p));

  async function handleHealthCheckAll() {
    try {
      await apiFetch('/api/v1/health/recompute-all', { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: ['platforms'] });
    } catch {
      // individual statuses updated via query invalidation
    }
  }

  async function handleRefreshStorage() {
    setRescanning(true);
    try {
      await apiFetch('/api/v1/health/storage/rescan', { method: 'POST' });
    } catch {
      // proceed to refetch even if rescan fails
    }
    setRescanning(false);
    refetchStorage();
  }

  function toggleCat(key: string) {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (permissionDenied) {
    return (
      <div className="flex flex-col min-h-full">
        <TopBar />
        <div className="p-6">
          <div
            className="rounded-xl p-6 text-sm"
            style={{
              background: 'rgb(var(--surface-1))',
              border: '1px solid rgb(var(--border))',
              color: 'rgb(var(--fg-3))',
            }}
          >
            You don't have permission to view platform health.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button
          type="button"
          onClick={handleHealthCheckAll}
          className="ml-auto rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-[120ms]"
          style={{
            fontFamily: 'var(--font-display)',
            background: 'rgb(var(--surface-2))',
            border: '1px solid rgb(var(--border))',
            color: 'rgb(var(--fg-1))',
            cursor: 'pointer',
          }}
        >
          Health Check All
        </button>
      </TopBar>

      <div className="p-6">
        {/* Status section */}
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
            Status
          </h2>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.8125rem',
              color: 'rgb(var(--fg-3))',
            }}
          >
            {healthy.length} healthy · {degraded.length} degraded
          </span>
          <div style={{ flex: 1 }} />
        </div>

        {degraded.length > 0 && (
          <div
            className="mb-4 flex gap-2.5 rounded-md px-3 py-2.5"
            style={{
              borderLeft: '3px solid rgb(var(--error))',
              background: 'rgb(var(--error) / 0.08)',
            }}
          >
            <span style={{ fontWeight: 600, color: 'rgb(var(--error))' }}>✗</span>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: '0.8125rem',
                lineHeight: 1.4,
                color: 'rgb(var(--fg-2))',
              }}
            >
              <strong>
                {degraded.length} platform{degraded.length > 1 ? 's need' : ' needs'} attention.
              </strong>{' '}
              Check your environment configuration or re-register.
            </span>
          </div>
        )}

        {isLoading ? (
          <div
            className="rounded-xl p-6 text-sm"
            style={{
              background: 'rgb(var(--surface-1))',
              border: '1px solid rgb(var(--border))',
              color: 'rgb(var(--fg-3))',
            }}
          >
            Loading…
          </div>
        ) : userPlatforms.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center text-sm"
            style={{
              border: '1px dashed rgb(var(--border-strong))',
              color: 'rgb(var(--fg-3))',
              backgroundImage:
                'repeating-linear-gradient(0deg, transparent 0 11px, rgb(var(--peach-500) / 0.04) 11px 12px), repeating-linear-gradient(90deg, transparent 0 11px, rgb(var(--peach-500) / 0.04) 11px 12px)',
            }}
          >
            No environments registered. Add environments to track platform health.
          </div>
        ) : (
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'rgb(var(--surface-1))', border: '1px solid rgb(var(--border))' }}
          >
            {userPlatforms.map((p, i) => {
              const ok = isHealthy(p);
              return (
                <div
                  key={p.id}
                  className="flex items-center gap-3.5 px-[18px] py-4"
                  style={{
                    borderBottom:
                      i < userPlatforms.length - 1 ? '1px solid rgb(var(--border))' : 'none',
                  }}
                >
                  <StatusDot healthy={ok} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2.5 mb-0.5">
                      <EraChip era={p.era} />
                      <span
                        style={{
                          fontFamily: 'var(--font-display)',
                          fontWeight: 600,
                          fontSize: '0.875rem',
                          color: 'rgb(var(--fg-1))',
                        }}
                      >
                        {p.name}
                      </span>
                    </div>
                    <div
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.75rem',
                        lineHeight: 1.4,
                        color: 'rgb(var(--fg-3))',
                      }}
                    >
                      Backend: {p.emulator_slug}
                      {p.working_image_path && ` · Working image: ${p.working_image_path}`}
                    </div>
                    {!ok && (
                      <div
                        className="mt-1.5 flex items-center gap-1.5"
                        style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: '0.75rem',
                          color: 'rgb(var(--warning))',
                        }}
                      >
                        <span>⚠</span>
                        <span>
                          {p.is_system ? 'Emulator not installed' : 'Working image not present'}
                        </span>
                      </div>
                    )}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.6875rem',
                      fontWeight: 500,
                      color: ok ? 'rgb(var(--success))' : 'rgb(var(--error))',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    <StatusDot healthy={ok} />
                    {ok ? 'Ready' : 'Degraded'}
                  </div>
                  {p.is_system && !ok && p.emulator_slug && (
                    <button
                      type="button"
                      onClick={() => navigate(`/emulators/${p.emulator_slug}`)}
                      style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        padding: '4px 10px',
                        borderRadius: 'var(--r-1)',
                        background: 'rgb(var(--surface-2))',
                        border: '1px solid rgb(var(--border))',
                        color: 'rgb(var(--peach-400))',
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Fix →
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Storage section */}
        <div className="mb-3 mt-7 flex items-baseline gap-2.5">
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
            Storage
          </h2>
          {storageFootprint && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.8125rem',
                color: 'rgb(var(--fg-3))',
              }}
            >
              {formatBytes(storageFootprint.total_bytes)} total
            </span>
          )}
          <div style={{ flex: 1 }} />
          <button
            type="button"
            onClick={handleRefreshStorage}
            disabled={storageLoading || rescanning}
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.75rem',
              fontWeight: 600,
              padding: '4px 10px',
              borderRadius: 'var(--r-1)',
              background: 'rgb(var(--surface-2))',
              border: '1px solid rgb(var(--border))',
              color: storageLoading || rescanning ? 'rgb(var(--fg-3))' : 'rgb(var(--fg-1))',
              cursor: storageLoading || rescanning ? 'default' : 'pointer',
              transition: 'opacity 120ms',
            }}
          >
            {rescanning ? 'Rescanning…' : storageLoading ? 'Scanning…' : 'Refresh'}
          </button>
        </div>

        <div
          className="rounded-xl overflow-hidden"
          style={{ background: 'rgb(var(--surface-1))', border: '1px solid rgb(var(--border))' }}
        >
          {storageLoading && !storageFootprint ? (
            <div
              className="px-[18px] py-5"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.8125rem',
                color: 'rgb(var(--fg-3))',
              }}
            >
              Scanning storage…
            </div>
          ) : !storageFootprint ? (
            <div
              className="px-[18px] py-5"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.8125rem',
                color: 'rgb(var(--fg-3))',
              }}
            >
              Storage data unavailable.
            </div>
          ) : (
            (() => {
              const total = storageFootprint.total_bytes;
              const pct = (n: number) =>
                total > 0 ? `${Math.max(1, (n / total) * 100).toFixed(1)}%` : '0%';

              return (
                <>
                  {/* Stacked bar */}
                  <div
                    className="flex overflow-hidden"
                    style={{ height: 6, background: 'rgb(var(--surface-2))' }}
                  >
                    {storageFootprint.categories.map((cat) => (
                      <span
                        key={cat.key}
                        style={{
                          width: pct(cat.size_bytes),
                          background: CAT_COLORS[cat.key] ?? 'rgb(var(--fg-3))',
                          transition: 'width 300ms ease',
                        }}
                      />
                    ))}
                  </div>

                  {/* Category rows */}
                  {storageFootprint.categories.map((cat) => {
                    const hasBreakdown = cat.breakdown.length > 0;
                    const expanded = expandedCats.has(cat.key);
                    const color = CAT_COLORS[cat.key] ?? 'rgb(var(--fg-3))';
                    const barWidth = total > 0 ? Math.max(0.5, (cat.size_bytes / total) * 100) : 0;

                    return (
                      <div key={cat.key}>
                        <div
                          className="flex items-center gap-3 px-[18px] py-3"
                          style={{
                            borderTop: '1px solid rgb(var(--border))',
                            cursor: hasBreakdown ? 'pointer' : 'default',
                          }}
                          onClick={hasBreakdown ? () => toggleCat(cat.key) : undefined}
                        >
                          <span
                            className="shrink-0 rounded-full"
                            style={{ width: 8, height: 8, background: color }}
                          />

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span
                                style={{
                                  fontFamily: 'var(--font-display)',
                                  fontWeight: 600,
                                  fontSize: '0.8125rem',
                                  color: 'rgb(var(--fg-1))',
                                }}
                              >
                                {cat.label}
                              </span>
                              {hasBreakdown && (
                                <span
                                  style={{
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.625rem',
                                    color: 'rgb(var(--fg-3))',
                                    transform: expanded ? 'rotate(90deg)' : 'none',
                                    display: 'inline-block',
                                    transition: 'transform 150ms',
                                  }}
                                >
                                  ▶
                                </span>
                              )}
                            </div>
                            <div
                              style={{
                                position: 'relative',
                                height: 4,
                                background: 'rgb(var(--surface-2))',
                                borderRadius: 2,
                                overflow: 'hidden',
                              }}
                            >
                              <div
                                style={{
                                  position: 'absolute',
                                  left: 0,
                                  top: 0,
                                  height: '100%',
                                  width: `${barWidth}%`,
                                  background: color,
                                  borderRadius: 2,
                                  transition: 'width 300ms ease',
                                }}
                              />
                            </div>
                            {cat.key === 'library_media' && (cat.unsized_count ?? 0) > 0 && (
                              <div
                                style={{
                                  fontFamily: 'var(--font-mono)',
                                  fontSize: '0.6875rem',
                                  color: 'rgb(var(--fg-3))',
                                  marginTop: 4,
                                }}
                              >
                                {cat.unsized_count} item{cat.unsized_count !== 1 ? 's' : ''} not yet
                                sized, size shown as unknown
                              </div>
                            )}
                          </div>

                          <div
                            style={{
                              fontFamily: 'var(--font-mono)',
                              fontWeight: 600,
                              fontSize: '0.8125rem',
                              color: 'rgb(var(--fg-1))',
                              minWidth: 72,
                              textAlign: 'right',
                            }}
                          >
                            {cat.size_bytes > 0 ? (
                              formatBytes(cat.size_bytes)
                            ) : (
                              <span style={{ color: 'rgb(var(--fg-3))', fontWeight: 400 }}>—</span>
                            )}
                          </div>
                        </div>

                        {/* Era breakdown */}
                        {hasBreakdown && expanded && (
                          <div
                            style={{
                              borderTop: '1px solid rgb(var(--border))',
                              background: 'rgb(var(--surface-0))',
                            }}
                          >
                            {cat.breakdown.map((row, ri) => {
                              const eraKey = ERA_LABEL[row.era] ?? row.era.toUpperCase();
                              const eraColor = ERA_COLOR[eraKey] ?? 'rgb(var(--fg-3))';
                              const eraLabel = ERA_LABEL[row.era] ?? row.label;
                              const eraBarWidth =
                                cat.size_bytes > 0
                                  ? Math.max(0.5, (row.size_bytes / cat.size_bytes) * 100)
                                  : 0;
                              return (
                                <div
                                  key={row.era}
                                  className="flex items-center gap-3 pl-10 pr-[18px] py-2.5"
                                  style={{
                                    borderBottom:
                                      ri < cat.breakdown.length - 1
                                        ? '1px solid rgb(var(--border))'
                                        : 'none',
                                  }}
                                >
                                  <span
                                    style={{
                                      fontFamily: 'var(--font-mono)',
                                      fontWeight: 600,
                                      fontSize: '0.625rem',
                                      letterSpacing: '0.08em',
                                      textTransform: 'uppercase',
                                      padding: '2px 5px',
                                      borderRadius: 'var(--r-1)',
                                      border: `1px solid ${eraColor}`,
                                      color: eraColor,
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {eraLabel}
                                  </span>
                                  <div className="flex-1 min-w-0">
                                    <div
                                      style={{
                                        position: 'relative',
                                        height: 3,
                                        background: 'rgb(var(--surface-2))',
                                        borderRadius: 2,
                                        overflow: 'hidden',
                                      }}
                                    >
                                      <div
                                        style={{
                                          position: 'absolute',
                                          left: 0,
                                          top: 0,
                                          height: '100%',
                                          width: `${eraBarWidth}%`,
                                          background: eraColor,
                                          borderRadius: 2,
                                          opacity: 0.7,
                                          transition: 'width 300ms ease',
                                        }}
                                      />
                                    </div>
                                  </div>
                                  <span
                                    style={{
                                      fontFamily: 'var(--font-mono)',
                                      fontSize: '0.6875rem',
                                      color: 'rgb(var(--fg-3))',
                                      minWidth: 36,
                                      textAlign: 'right',
                                    }}
                                  >
                                    {row.count} item{row.count !== 1 ? 's' : ''}
                                  </span>
                                  <span
                                    style={{
                                      fontFamily: 'var(--font-mono)',
                                      fontWeight: 600,
                                      fontSize: '0.75rem',
                                      color: 'rgb(var(--fg-1))',
                                      minWidth: 72,
                                      textAlign: 'right',
                                    }}
                                  >
                                    {formatBytes(row.size_bytes)}
                                  </span>
                                </div>
                              );
                            })}
                            {(cat.unsized_count ?? 0) > 0 && (
                              <div
                                className="flex items-center gap-3 pl-10 pr-[18px] py-2.5"
                                style={{
                                  borderTop:
                                    cat.breakdown.length > 0
                                      ? '1px solid rgb(var(--border))'
                                      : 'none',
                                  opacity: 0.6,
                                }}
                              >
                                <span
                                  style={{
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.6875rem',
                                    color: 'rgb(var(--fg-3))',
                                  }}
                                >
                                  {cat.unsized_count} item{cat.unsized_count !== 1 ? 's' : ''} —
                                  size unknown
                                </span>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </>
              );
            })()
          )}
        </div>

        {/* Inventory section */}
        <div className="mb-3 mt-7 flex items-baseline gap-2.5">
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
            Inventory
          </h2>
        </div>

        {(() => {
          const stats: { label: string; value: string; sub?: string }[] = summary
            ? [
                {
                  label: 'library items',
                  value: summary.library.total.toString(),
                },
                {
                  label: 'emulators',
                  value: summary.emulators.installed.toString(),
                  sub: `of ${summary.emulators.total} in catalog`,
                },
                {
                  label: 'drives',
                  value: summary.drives.total.toString(),
                },
                {
                  label: 'media formats',
                  value: summary.extensions.total.toString(),
                },
                {
                  label: 'bios sets',
                  value: summary.bios.present.toString(),
                  sub: `of ${summary.bios.total} required`,
                },
                {
                  label: 'rom packs',
                  value: summary.rom_packs.installed.toString(),
                  sub: `of ${summary.rom_packs.total} in catalog`,
                },
              ]
            : [];

          return (
            <div
              className="rounded-xl p-[18px]"
              style={{
                background: 'rgb(var(--surface-1))',
                border: '1px solid rgb(var(--border))',
              }}
            >
              {summaryLoading ? (
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.8125rem',
                    color: 'rgb(var(--fg-3))',
                  }}
                >
                  Loading…
                </div>
              ) : summaryError || !summary ? (
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.8125rem',
                    color: 'rgb(var(--fg-3))',
                  }}
                >
                  Inventory unavailable, run a health check to refresh.
                </div>
              ) : (
                <div
                  className="grid gap-x-[18px] gap-y-4"
                  style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}
                >
                  {stats.map(({ label, value, sub }) => (
                    <div key={label}>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 700,
                          fontSize: '1.375rem',
                          lineHeight: 1,
                          color: 'rgb(var(--fg-1))',
                        }}
                      >
                        {value}
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.6875rem',
                          color: 'rgb(var(--fg-3))',
                          marginTop: 4,
                        }}
                      >
                        {label}
                      </div>
                      {sub && (
                        <div
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.625rem',
                            color: 'rgb(var(--fg-3))',
                            opacity: 0.7,
                            marginTop: 2,
                          }}
                        >
                          {sub}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
