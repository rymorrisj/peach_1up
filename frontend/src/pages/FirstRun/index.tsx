import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { apiFetch, ApiError } from '@/api/client';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import StepWelcome from './StepWelcome';
import Step0Owner from './Step0Owner';
import StepSoftware from './StepSoftware';
import StepUsers from './StepUsers';
import StepEmulators from './StepEmulators';
import StepBios from './StepBios';
import StepSettings from './StepSettings';
import StepGuides from './StepGuides';
import type { FirstRunStatus } from './types';

// Local step index for the screens shown across the wizard. Not a
// generalized Stepper, this is a fixed, hand-ordered sequence, not a
// config-driven array, and isn't expected to grow much beyond this.
type WizardStep =
  'welcome' | 'owner' | 'software' | 'users' | 'emulators' | 'bios' | 'settings' | 'guides';

export default function FirstRun() {
  const [completeError, setCompleteError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [step, setStep] = useState<WizardStep | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch<FirstRunStatus>('/api/v1/settings/first-run-status'),
  });

  if (isLoading || finishing) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-0">
        <LoadingSpinner label="Checking setup status…" />
      </main>
    );
  }

  if (data?.first_run_complete) return <Navigate to="/software" replace />;

  // Owner already exists (e.g. the wizard was reloaded mid-flow), resume at
  // the first step after owner creation instead of re-showing it, and skip
  // Welcome too, since it has nothing to do with the owner-exists check.
  // A true first-time visitor (no owner yet) always starts at Welcome.
  const currentStep: WizardStep = step ?? (data?.owner_exists ? 'software' : 'welcome');

  async function completeSetup(target: string = '/') {
    setFinishing(true);
    setCompleteError(null);
    try {
      await apiFetch('/api/v1/settings/complete-first-run', { method: 'POST' });
      // Hard reload (not a client-side navigate) is deliberate: it forces
      // AppProvider's auth check and every route guard's first-run-status
      // query to refetch fresh instead of reading the now-stale cached
      // "incomplete" result, which would otherwise bounce back here.
      window.location.replace(target);
    } catch (err) {
      setCompleteError(err instanceof ApiError ? err.detail : 'Setup could not be completed.');
      setFinishing(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface-0 px-6 py-12">
      <div className="w-full max-w-2xl">
        {completeError && (
          <p role="alert" className="mb-4 text-sm text-error">
            {completeError}
          </p>
        )}
        {currentStep === 'welcome' && <StepWelcome onNext={() => setStep('owner')} />}
        {currentStep === 'owner' && <Step0Owner onNext={() => setStep('software')} />}
        {currentStep === 'software' && <StepSoftware onNext={() => setStep('users')} />}
        {currentStep === 'users' && (
          <StepUsers onBack={() => setStep('software')} onNext={() => setStep('emulators')} />
        )}
        {currentStep === 'emulators' && (
          <StepEmulators
            emulators={data?.emulators ?? []}
            onNext={() => setStep('bios')}
            onSkip={() => setStep('settings')}
            onFinishAndGoTo={completeSetup}
          />
        )}
        {currentStep === 'bios' && (
          <StepBios
            onBack={() => setStep('emulators')}
            onFinish={() => setStep('settings')}
            onFinishAndGoTo={completeSetup}
            finishing={finishing}
          />
        )}
        {currentStep === 'settings' && (
          <StepSettings onBack={() => setStep('bios')} onNext={() => setStep('guides')} />
        )}
        {currentStep === 'guides' && (
          <StepGuides
            onBack={() => setStep('settings')}
            onFinish={() => completeSetup()}
            finishing={finishing}
          />
        )}
      </div>
    </main>
  );
}
