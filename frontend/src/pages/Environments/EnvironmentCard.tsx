import { Button } from '@/ui'
import { ERA_LABELS } from '@/generated/constants'
import type { components } from '@shared/types'
import EmulatorStatus from '@/components/emulators/EmulatorStatus'
import LaunchHistory from '@/components/launches/LaunchHistory'
import { useLaunch } from '@/hooks/useLaunch'

type Platform = components['schemas']['PlatformRead']

const EMULATOR_LABELS: Record<string, string> = {
  'dosbox-x': 'DOSBox-X',
  virtualbox: 'VirtualBox',
}

interface EnvironmentCardProps {
  platform: Platform
  healthLoading: boolean
  onEdit: (platform: Platform) => void
  onDelete: (platform: Platform) => void
  onHealthCheck: (platform: Platform) => void
}

export default function EnvironmentCard({
  platform,
  healthLoading,
  onEdit,
  onDelete,
  onHealthCheck,
}: EnvironmentCardProps) {
  const eraLabel = ERA_LABELS[platform.era] ?? platform.era
  const emulatorLabel = EMULATOR_LABELS[platform.emulator_slug] ?? platform.emulator_slug
  const { launch, stop, isLaunching, error: launchError, warnings } = useLaunch(
    platform.id,
    'environment',
  )

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-700 dark:bg-surface-800">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-medium text-neutral-900 dark:text-neutral-100">
            {platform.name}
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-neutral-100 text-neutral-600 dark:bg-surface-700 dark:text-neutral-300">
              {eraLabel}
            </span>
            <span className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
              {emulatorLabel}
            </span>
          </div>
        </div>
        <EmulatorStatus status={platform.status} />
      </div>

      {(platform.base_image_path || platform.working_image_path) && (
        <div className="space-y-1 rounded-md bg-neutral-50 px-3 py-2 dark:bg-surface-900">
          {platform.base_image_path && (
            <div className="flex gap-2 text-xs">
              <span className="shrink-0 text-neutral-400 dark:text-neutral-500">Base:</span>
              <span className="min-w-0 flex-1 truncate font-mono text-neutral-600 dark:text-neutral-300">
                {platform.base_image_path}
              </span>
            </div>
          )}
          {platform.working_image_path && (
            <div className="flex gap-2 text-xs">
              <span className="shrink-0 text-neutral-400 dark:text-neutral-500">Working:</span>
              <span className="min-w-0 flex-1 truncate font-mono text-neutral-600 dark:text-neutral-300">
                {platform.working_image_path}
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
          <Button size="sm" onClick={launch}>
            Launch
          </Button>
        )}
        <Button variant="secondary" size="sm" onClick={() => onEdit(platform)}>
          Edit
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onHealthCheck(platform)}
          loading={healthLoading}
          disabled={healthLoading}
        >
          Health Check
        </Button>
        <Button variant="destructive" size="sm" onClick={() => onDelete(platform)}>
          Delete
        </Button>
      </div>

      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((w: string, i: number) => (
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

      <LaunchHistory targetId={platform.id} targetType="environment" />
    </div>
  )
}
