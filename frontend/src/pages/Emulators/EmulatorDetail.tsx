import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import TopBar from '@/components/layout/TopBar';
import ConfirmModal from '@/components/common/ConfirmModal';
import { useConfirm } from '@/hooks/useConfirm';
import { useAppContext } from '@/context/useAppContext';
import { EMULATOR_ERA_MAP, ERA_COLOR } from '@/types/era';
import { useToast } from '@/ui/ToastProvider';
import type { EmulatorStatusData } from '@/pages/FirstRun/types';
import type { components } from '@shared/types';
import { TabBtn, type Tab } from './components/EmulatorDetailPrimitives';
import { OverviewTab } from './components/OverviewTab';
import { RomPackTab } from './components/RomPackTab';
import { ExtensionsTab } from './components/ExtensionsTab';
import { LimitationsTab } from './components/LimitationsTab';
type CatalogEntry = components['schemas']['CatalogEntryResponse'];
type LaunchProfile = components['schemas']['ProfileItemRead'];
type BiosItem = components['schemas']['BiosItem'];
type LaunchHistory = components['schemas']['LaunchHistoryRead'];

const EMULATOR_BIOS_PLATFORM: Record<string, string> = {
  duckstation: 'ps1',
  pcsx2: 'ps2',
  xemu: 'xbox',
  flycast: 'dreamcast',
  '86box': '86box',
  mesen: 'mesen',
};

export default function EmulatorDetail() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { state } = useAppContext();
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm();
  const [tab, setTab] = useState<Tab>('overview');
  const [sandboxSaving, setSandboxSaving] = useState(false);
  const [isInstalling, setIsInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [isCloning, setIsCloning] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);
  const [isForceClosing, setIsForceClosing] = useState(false);

  const { data: catalog = [] } = useQuery<CatalogEntry[]>({
    queryKey: ['emulators-catalog'],
    queryFn: () => apiFetch<CatalogEntry[]>('/api/v1/emulator-items'),
    staleTime: 10_000,
  });

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: async () =>
      (await apiFetch<{ items: LaunchProfile[] }>('/api/v1/profile-items?limit=200')).items,
  });

  const entry = catalog.find((e) => e.slug === slug);
  const romPackSlug = entry?.rom_pack_slug ?? undefined;
  const emulatorBiosPlatform = slug ? EMULATOR_BIOS_PLATFORM[slug] : undefined;

  // Lookup-only consumer of GET /api/v1/bios (now Page[BiosItem]) —
  // unwraps .items, capped at limit=200 (same pattern as the /api/v1/profile-items
  // lookup consumers), not expected to exceed that at current catalog scale.
  const { data: allBios = [] } = useQuery<BiosItem[]>({
    queryKey: ['bios-requirements'],
    queryFn: async () => (await apiFetch<{ items: BiosItem[] }>('/api/v1/bios?limit=200')).items,
    enabled: !!emulatorBiosPlatform,
  });

  const { data: installStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', slug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulator-items/${slug}/status`),
    refetchInterval: isInstalling ? 3000 : false,
    enabled: isInstalling && !!slug,
  });

  const { data: cloneStatus } = useQuery<EmulatorStatusData>({
    queryKey: ['emulator-status', romPackSlug],
    queryFn: () => apiFetch<EmulatorStatusData>(`/api/v1/emulator-items/${romPackSlug}/status`),
    refetchInterval: isCloning ? 4000 : false,
    enabled: isCloning && !!romPackSlug,
  });

  // Same queryKey/queryFn as TopBar's own launches query, so both share one
  // cache entry and one poll instead of issuing duplicate requests.
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

  // The launch guard blocks a second concurrent launch for the same
  // emulator/profile, so at most one running launch can match this slug.
  const runningLaunch = launches.find((l) => l.emulator_slug === slug && l.ended_at === null);
  const isRunning = !!runningLaunch;

  // container_moniker is only computed by the detail endpoint (GET
  // /api/v1/launches/{id}), not the list endpoint the ['launches'] query
  // above uses, so it takes its own fetch, scoped to the running launch's id.
  const { data: runningLaunchDetail } = useQuery<LaunchHistory>({
    queryKey: ['launches', runningLaunch?.id],
    queryFn: () => apiFetch<LaunchHistory>(`/api/v1/launches/${runningLaunch!.id}`),
    enabled: !!runningLaunch,
  });
  const containerMoniker = runningLaunchDetail?.container_moniker ?? null;

  const romPackEntry = romPackSlug ? catalog.find((e) => e.slug === romPackSlug) : undefined;
  const emulatorBios = allBios.filter((b) => b.platform === emulatorBiosPlatform);
  const eras = slug ? (EMULATOR_ERA_MAP[slug] ?? []) : [];
  const emulatorProfiles = profiles.filter((p) => p.emulator_slug === slug);
  const isReady = entry?.is_installed && entry?.install_path;

  useEffect(() => {
    if (!installStatus) return;
    if (installStatus.binary_detected) {
      setIsInstalling(false);
      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
    }
    if (installStatus.status === 'error') {
      setIsInstalling(false);
      setInstallError(installStatus.error ?? 'Install failed.');
    }
  }, [installStatus]);

  useEffect(() => {
    if (!cloneStatus) return;
    if (cloneStatus.status === 'complete') {
      setIsCloning(false);
      queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
    }
    if (cloneStatus.status === 'error') {
      setIsCloning(false);
      setCloneError(cloneStatus.error ?? 'Clone failed.');
    }
  }, [cloneStatus]);

  async function handleSandboxToggle(
    field: 'container_enabled' | 'skip_cpu_limit' | 'skip_memory_limit',
    value: boolean,
  ) {
    if (!slug || sandboxSaving) return;
    setSandboxSaving(true);
    try {
      await apiFetch(`/api/v1/emulator-items/${slug}/sandbox`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      });
      await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
    } finally {
      setSandboxSaving(false);
    }
  }

  async function handleDelete() {
    if (!slug || !entry) return;
    if (
      !window.confirm(
        `Remove "${entry.name}"? This unregisters the binary but does not delete files.`,
      )
    )
      return;
    try {
      const { token } = await apiFetch<{ token: string }>(
        `/api/v1/emulator-items/${slug}/confirm-token`,
      );
      await apiFetch(`/api/v1/emulator-items/${slug}`, {
        method: 'DELETE',
        body: JSON.stringify({ confirmation_token: token }),
      });
      await queryClient.invalidateQueries({ queryKey: ['emulators-catalog'] });
      navigate('/emulators');
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Remove failed.', 'error');
    }
  }

  async function handleForceClose() {
    if (!runningLaunch || isForceClosing) return;
    const confirmed = await confirm({
      title: `Force close ${entry?.name ?? slug}?`,
      consequence: 'This immediately terminates the running process. Unsaved progress in the emulator will be lost.',
      destructive: true,
    });
    if (!confirmed) return;
    setIsForceClosing(true);
    try {
      const result = await apiFetch<{ stopped: boolean }>(
        `/api/v1/launches/${runningLaunch.id}/stop`,
        { method: 'POST' },
      );
      await queryClient.invalidateQueries({ queryKey: ['launches'] });
      if (!result.stopped) {
        showToast('Process had already stopped.', 'info');
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Force close failed.', 'error');
    } finally {
      setIsForceClosing(false);
    }
  }

  async function handleRunInstaller() {
    if (!slug) return;
    setIsInstalling(true);
    setInstallError(null);
    try {
      await apiFetch(`/api/v1/emulator-items/${slug}/install`, { method: 'POST' });
    } catch (err) {
      setIsInstalling(false);
      setInstallError(err instanceof ApiError ? err.detail : 'Failed to launch installer.');
    }
  }

  async function handleCloneRomPack() {
    if (!romPackSlug) return;
    setIsCloning(true);
    setCloneError(null);
    try {
      await apiFetch(`/api/v1/emulator-items/${romPackSlug}/install`, { method: 'POST' });
    } catch (err) {
      setIsCloning(false);
      setCloneError(err instanceof ApiError ? err.detail : 'Failed to start clone.');
    }
  }

  if (catalog.length > 0 && !entry) {
    return (
      <div className="p-6" style={{ color: 'rgb(var(--fg-3))' }}>
        Emulator not found.
      </div>
    );
  }

  const BTN: React.CSSProperties = {
    border: 'none',
    fontFamily: 'var(--font-display)',
    fontSize: '0.8125rem',
    fontWeight: 600,
    padding: '9px 14px',
    borderRadius: 'var(--r-2)',
    cursor: 'pointer',
  };

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button
          type="button"
          onClick={() => navigate('/emulators')}
          style={{
            background: 'transparent',
            border: 0,
            color: 'rgb(var(--fg-1))',
            fontFamily: 'var(--font-display)',
            fontSize: '0.8125rem',
            fontWeight: 500,
            cursor: 'pointer',
            padding: '6px 10px',
          }}
        >
          ← Emulators
        </button>
        <span style={{ flex: 1 }} />
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
          style={
            isRunning
              ? {
                  background: 'rgb(var(--success) / 0.12)',
                  color: 'rgb(var(--success))',
                  border: '1px solid rgb(var(--success) / 0.3)',
                }
              : {
                  background: 'rgb(var(--surface-2))',
                  color: 'rgb(var(--fg-3))',
                  border: '1px solid rgb(var(--border))',
                }
          }
        >
          {isRunning && (
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: 'rgb(var(--success))',
                animation: 'dot-pulse 1.4s ease-in-out infinite',
              }}
              aria-hidden="true"
            />
          )}
          {isRunning ? 'Running' : 'Not running'}
        </span>
        {/* Only ever populated for AppContainer-enabled launches, the API
            leaves container_moniker null for Job-Object-only launches, so
            gating on the field itself (not container_enabled client-side)
            keeps this hidden for those automatically. */}
        {containerMoniker && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.6875rem',
              color: 'rgb(var(--fg-3))',
            }}
          >
            {containerMoniker}
          </span>
        )}
        {isRunning && (
          <button
            type="button"
            onClick={handleForceClose}
            disabled={isForceClosing}
            style={{
              ...BTN,
              background: 'transparent',
              border: '1px solid rgb(var(--error))',
              color: 'rgb(var(--error))',
              opacity: isForceClosing ? 0.5 : 1,
            }}
          >
            {isForceClosing ? 'Closing…' : 'Force Close'}
          </button>
        )}
        <button
          type="button"
          onClick={handleDelete}
          style={{
            ...BTN,
            background: 'transparent',
            border: '1px solid rgb(var(--error))',
            color: 'rgb(var(--error))',
          }}
        >
          Remove
        </button>
      </TopBar>

      <div className="p-6">
        {/* Header */}
        <div className="flex items-center gap-3.5 mb-1.5">
          <div
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              width: 56,
              height: 56,
              background: 'rgb(var(--surface-2))',
              border: '1px solid rgb(var(--border-strong))',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: '1.375rem',
              color: 'rgb(var(--peach-300))',
            }}
          >
            {entry ? entry.name.slice(0, 2).toUpperCase() : '??'}
          </div>
          <div>
            <h1
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '2rem',
                letterSpacing: '-0.02em',
                margin: 0,
                color: 'rgb(var(--fg-1))',
              }}
            >
              {entry?.name ?? slug}
            </h1>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.8125rem',
                color: 'rgb(var(--fg-3))',
                marginTop: 6,
              }}
            >
              {entry?.version}
            </div>
          </div>
          <span style={{ flex: 1 }} />
          <div className="flex gap-1.5">
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
        </div>

        {entry && (
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.875rem',
              lineHeight: 1.55,
              color: 'rgb(var(--fg-2))',
              maxWidth: 760,
              margin: '14px 0 22px',
            }}
          >
            {entry.description}
          </p>
        )}

        {/* Tabs */}
        <div
          className="flex gap-0"
          style={{ borderBottom: '1px solid rgb(var(--border))', marginBottom: 18 }}
        >
          <TabBtn
            id="overview"
            label="Overview"
            active={tab === 'overview'}
            onClick={() => setTab('overview')}
          />
          {romPackSlug && (
            <TabBtn
              id="rom"
              label="ROM Packs"
              active={tab === 'rom'}
              onClick={() => setTab('rom')}
            />
          )}
          <TabBtn
            id="ext"
            label="Extensions"
            active={tab === 'ext'}
            onClick={() => setTab('ext')}
          />
          {(entry?.known_limitations?.length ?? 0) > 0 && (
            <TabBtn
              id="limits"
              label="Known Limitations"
              count={entry!.known_limitations!.length}
              active={tab === 'limits'}
              onClick={() => setTab('limits')}
            />
          )}
        </div>

        {tab === 'overview' && entry && (
          <OverviewTab
            entry={entry}
            eras={eras}
            isReady={isReady}
            emulatorProfilesCount={emulatorProfiles.length}
            emulatorBios={emulatorBios}
            sandboxSaving={sandboxSaving}
            onSandboxToggle={handleSandboxToggle}
            onShowLimitations={() => setTab('limits')}
            isInstalling={isInstalling}
            installError={installError}
            onRunInstaller={handleRunInstaller}
            romPackEntry={romPackEntry}
            isCloning={isCloning}
            cloneError={cloneError}
            onCloneRomPack={handleCloneRomPack}
          />
        )}

        {tab === 'rom' && (
          <RomPackTab
            romPackEntry={romPackEntry}
            isCloning={isCloning}
            cloneError={cloneError}
            onCloneRomPack={handleCloneRomPack}
          />
        )}

        {tab === 'ext' && <ExtensionsTab entry={entry} />}

        {tab === 'limits' && entry && <LimitationsTab entry={entry} />}
      </div>

      <ConfirmModal
        open={isOpen}
        title={options?.title ?? ''}
        consequence={options?.consequence ?? ''}
        destructive={options?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  );
}
