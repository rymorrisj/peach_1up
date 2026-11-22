import { useNavigate } from 'react-router-dom';
import { Button } from '@/ui';
import ConfirmModal from '@/components/common/ConfirmModal';
import EmulatorStatus from '@/components/emulators/EmulatorStatus';
import { PLATFORM_LABELS } from '@/generated/constants';
import type { components } from '@shared/types';
import LaunchHistory from '@/components/launches/LaunchHistory';
import { useLaunch } from '@/hooks/useLaunch';
import { useEnvironmentInstalledToggle } from '@/hooks/useEnvironmentInstalledToggle';

type EnvironmentBase = components['schemas']['EnvironmentItemRead'];
type Environment = EnvironmentBase & { installed_at?: string | null };

const EMULATOR_LABELS: Record<string, string> = {
  'dosbox-x': 'DOSBox-X',
  '86box': '86Box',
};

interface EnvironmentCardProps {
  environment: EnvironmentBase;
  healthLoading: boolean;
  onEdit: (environment: EnvironmentBase) => void;
  onDelete: (environment: EnvironmentBase) => void;
  onHealthCheck: (environment: EnvironmentBase) => void;
}

export default function EnvironmentCard({
  environment: environmentBase,
  healthLoading,
  onEdit,
  onDelete,
  onHealthCheck,
}: EnvironmentCardProps) {
  const environment = environmentBase as Environment;
  const navigate = useNavigate();
  const platformLabel = PLATFORM_LABELS[environment.platform] ?? environment.platform;
  const emulatorLabel = EMULATOR_LABELS[environment.emulator_slug] ?? environment.emulator_slug;
  const {
    launch,
    stop,
    isLaunching,
    error: launchError,
    launchWarnings,
  } = useLaunch({
    targetId: environment.id,
    targetType: 'environment',
  });

  const {
    handleToggleInstalled,
    isPending: installedPending,
    installedError: markInstalledError,
    confirmOpen: installedConfirmOpen,
    confirmOptions: installedConfirmOptions,
    handleConfirm: handleInstalledConfirm,
    handleCancel: handleInstalledCancel,
  } = useEnvironmentInstalledToggle({ environmentId: environment.id });

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-surface-1 p-4 dark:border-neutral-700">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-medium text-neutral-900 dark:text-neutral-100">
            <button
              type="button"
              onClick={() => navigate(`/environments/${environment.id}`)}
              className="hover:underline"
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                fontWeight: 'inherit',
                fontSize: 'inherit',
                color: 'inherit',
                fontFamily: 'inherit',
              }}
            >
              {environment.name}
            </button>
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-surface-3 text-neutral-600 dark:text-neutral-300">
              {platformLabel}
            </span>
            <span className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
              {emulatorLabel}
            </span>
            {environment.installed_at && (
              <span className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                Installed
              </span>
            )}
          </div>
        </div>
        <EmulatorStatus status={environment.is_present ? 'ok' : 'missing'} />
      </div>

      {(environment.base_image_path || environment.working_image_path) && (
        <div className="space-y-1 rounded-md bg-surface-1 px-3 py-2">
          {environment.base_image_path && (
            <div className="flex gap-2 text-xs">
              <span className="shrink-0 text-neutral-400 dark:text-neutral-500">Base:</span>
              <span className="min-w-0 flex-1 truncate font-mono text-neutral-600 dark:text-neutral-300">
                {environment.base_image_path}
              </span>
            </div>
          )}
          {environment.working_image_path && (
            <div className="flex gap-2 text-xs">
              <span className="shrink-0 text-neutral-400 dark:text-neutral-500">Working:</span>
              <span className="min-w-0 flex-1 truncate font-mono text-neutral-600 dark:text-neutral-300">
                {environment.working_image_path}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {isLaunching ? (
          <Button size="sm" variant="destructive" onClick={stop}>
            Stop
          </Button>
        ) : (
          <Button size="sm" onClick={() => launch()}>
            Launch
          </Button>
        )}
        {!environment.installed_at && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => handleToggleInstalled(false)}
            loading={installedPending}
            disabled={installedPending}
          >
            Mark as Installed
          </Button>
        )}
        <Button variant="secondary" size="sm" onClick={() => onEdit(environmentBase)}>
          Edit
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onHealthCheck(environmentBase)}
          loading={healthLoading}
          disabled={healthLoading}
        >
          Health Check
        </Button>
        <Button variant="destructive" size="sm" onClick={() => onDelete(environmentBase)}>
          Delete
        </Button>
      </div>

      {markInstalledError && (
        <p role="alert" className="text-xs text-error">
          ❌ {markInstalledError}
        </p>
      )}

      {launchWarnings.length > 0 && (
        <div className="space-y-1">
          {launchWarnings.map((w: string, i: number) => (
            <p key={i} className="text-xs text-amber-600 dark:text-amber-400">
              ⚠ {w}
            </p>
          ))}
        </div>
      )}

      {launchError && (
        <p role="alert" className="text-xs text-error">
          ❌ {launchError}
        </p>
      )}

      <LaunchHistory targetId={environment.id} targetType="environment_item" />

      <ConfirmModal
        open={installedConfirmOpen}
        title={installedConfirmOptions?.title ?? ''}
        consequence={installedConfirmOptions?.consequence ?? ''}
        destructive={installedConfirmOptions?.destructive}
        onConfirm={handleInstalledConfirm}
        onCancel={handleInstalledCancel}
      />
    </div>
  );
}
