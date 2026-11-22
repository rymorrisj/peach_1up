import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import { Button } from '@/ui';
import TopBar from '@/components/layout/TopBar';
import ConfirmModal from '@/components/common/ConfirmModal';
import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useConfirm } from '@/hooks/useConfirm';
import { useToast } from '@/ui/ToastProvider';
import type { components } from '@shared/types';
import EnvironmentCard from './EnvironmentCard';
import EnvironmentModal from './EnvironmentModal';
import {
  type EnvironmentForm,
  BOX86_PLATFORMS,
  EMPTY_ENV_FORM,
  PLATFORM_TO_EMULATOR,
} from './environmentForm';

type Environment = components['schemas']['EnvironmentItemRead'];

type EnvModalState = null | { mode: 'create' } | { mode: 'edit'; environment: Environment };

function formFromEnvironment(p: Environment): EnvironmentForm {
  const ext = p as Environment & {
    hardware_profile?: string;
    machine_override?: string;
    launch_commands?: string[] | null;
  };
  return {
    name: p.name,
    platform: p.platform as EnvironmentForm['platform'],
    base_image_path: p.base_image_path ?? '',
    working_image_path: p.working_image_path ?? '',
    hardware_profile: (ext.hardware_profile ?? 'standard') as EnvironmentForm['hardware_profile'],
    machine_override: ext.machine_override ?? '',
    notes: p.notes ?? '',
    launch_commands: ext.launch_commands ?? [],
  };
}

export default function Environments() {
  const queryClient = useQueryClient();
  const { confirm, isOpen, options, handleConfirm, handleCancel } = useConfirm();
  const { showToast } = useToast();

  const { data: environments, isLoading } = useQuery<Environment[]>({
    queryKey: ['environments'],
    queryFn: () => apiFetch<Environment[]>('/api/v1/environment-items'),
  });

  const userEnvironments = (environments ?? []).filter((p) => !p.is_system);

  const [modal, setModal] = useState<EnvModalState>(null);
  const [form, setForm] = useState<EnvironmentForm>(EMPTY_ENV_FORM);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof EnvironmentForm, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [healthLoading, setHealthLoading] = useState<number | null>(null);
  const [healthCheckAllRunning, setHealthCheckAllRunning] = useState(false);

  function openCreate() {
    setForm(EMPTY_ENV_FORM);
    setFormErrors({});
    setSubmitError(null);
    setModal({ mode: 'create' });
  }

  function openEdit(environment: Environment) {
    setForm(formFromEnvironment(environment));
    setFormErrors({});
    setSubmitError(null);
    setModal({ mode: 'edit', environment });
  }

  function closeModal() {
    setModal(null);
  }

  function setField<K extends keyof EnvironmentForm>(key: K, value: EnvironmentForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFormErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function validate(): boolean {
    const errors: Partial<Record<keyof EnvironmentForm, string>> = {};
    if (!form.name.trim()) errors.name = 'Name is required.';
    if (!form.platform) errors.platform = 'Select an environment platform.';
    if (
      modal?.mode === 'create' &&
      form.platform &&
      BOX86_PLATFORMS.has(form.platform) &&
      !form.base_image_path.trim()
    ) {
      errors.base_image_path = 'Installation media is required for this platform.';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const platform = form.platform!;
      const body = {
        name: form.name.trim(),
        platform,
        emulator_slug: PLATFORM_TO_EMULATOR[platform],
        base_image_path: form.base_image_path.trim() || null,
        working_image_path: form.working_image_path.trim() || null,
        hardware_profile: form.hardware_profile,
        machine_override: form.machine_override.trim() || null,
        notes: form.notes.trim() || null,
        launch_commands: form.launch_commands,
      };
      if (modal?.mode === 'create') {
        await apiFetch('/api/v1/environment-items', { method: 'POST', body: JSON.stringify(body) });
      } else if (modal?.mode === 'edit') {
        await apiFetch(`/api/v1/environment-items/${modal.environment.id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      }
      await queryClient.invalidateQueries({ queryKey: ['environments'] });
      closeModal();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : 'Something went wrong.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(environment: Environment) {
    const confirmed = await confirm({
      title: `Delete "${environment.name}"?`,
      consequence: 'This removes the environment registration. OS images on disk are not deleted.',
      destructive: true,
    });
    if (!confirmed) return;
    try {
      const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(
        `/api/v1/environment-items/${environment.id}/confirm-delete`,
        { method: 'POST' },
      );
      await apiFetch(
        `/api/v1/environment-items/${environment.id}?confirmation_token=${encodeURIComponent(confirmation_token)}`,
        { method: 'DELETE' },
      );
      await queryClient.invalidateQueries({ queryKey: ['environments'] });
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Delete failed.', 'error');
    }
  }

  async function handleHealthCheck(environment: Environment) {
    setHealthLoading(environment.id);
    try {
      await apiFetch(`/api/v1/environment-items/${environment.id}/health`, { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: ['environments'] });
      // An unhealthy *result* is not an error here, it's a 200 whose status
      // update is reflected via the invalidation above. Only a failed request
      // itself (network/permission/500) reaches this catch.
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Health check request failed.', 'error');
    } finally {
      setHealthLoading(null);
    }
  }

  async function handleHealthCheckAll() {
    setHealthCheckAllRunning(true);
    try {
      await apiFetch('/api/v1/health/recompute-all', { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: ['environments'] });
      // Per-environment failures are handled server-side and reflected via the
      // invalidation above; only a failed request itself reaches this catch.
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Health check request failed.', 'error');
    } finally {
      setHealthCheckAllRunning(false);
    }
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Environments" showStatus>
        <Button
          variant="secondary"
          onClick={handleHealthCheckAll}
          loading={healthCheckAllRunning}
          disabled={healthCheckAllRunning || isLoading}
        >
          Health Check All
        </Button>
        <Button onClick={openCreate}>+ Add Environment</Button>
      </TopBar>

      <div className="p-6">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
            <LoadingSpinner label="Loading environments…" />
            <span aria-hidden="true">Loading environments…</span>
          </div>
        ) : userEnvironments.length === 0 ? (
          <EmptyState
            heading="No environments yet"
            subtext="Add an environment to register a PC OS image for launching."
            cta={{ label: 'Add Environment', onClick: openCreate }}
          />
        ) : (
          <div className="space-y-3">
            {userEnvironments.map((environment) => (
              <EnvironmentCard
                key={environment.id}
                environment={environment}
                healthLoading={healthLoading === environment.id}
                onEdit={openEdit}
                onDelete={handleDelete}
                onHealthCheck={handleHealthCheck}
              />
            ))}
          </div>
        )}
      </div>

      <EnvironmentModal
        open={modal !== null}
        mode={modal?.mode ?? 'create'}
        slug={modal?.mode === 'edit' ? (modal.environment.slug ?? undefined) : undefined}
        form={form}
        formErrors={formErrors}
        submitError={submitError}
        submitting={submitting}
        onClose={closeModal}
        onSubmit={handleSubmit}
        onFieldChange={setField}
      />

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
