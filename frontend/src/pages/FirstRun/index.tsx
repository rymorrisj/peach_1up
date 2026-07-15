import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { apiFetch, ApiError } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import Step0Owner from './Step0Owner'
import StepEmulators from './StepEmulators'
import StepBios from './StepBios'
import type { FirstRunStatus } from './types'

// Local step index for the two informational screens shown after the owner
// account exists. Not a generalized Stepper, this wizard is fixed at three
// screens and isn't expected to grow.
type WizardStep = 'owner' | 'emulators' | 'bios'

export default function FirstRun() {
  const [completeError, setCompleteError] = useState<string | null>(null)
  const [finishing, setFinishing] = useState(false)
  const [step, setStep] = useState<WizardStep | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch<FirstRunStatus>('/api/v1/settings/first-run-status'),
  })

  if (isLoading || finishing) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950">
        <LoadingSpinner label="Checking setup status…" />
      </main>
    )
  }

  if (data?.first_run_complete) return <Navigate to="/software" replace />

  // Owner already exists (e.g. the wizard was reloaded mid-flow) — resume at
  // the informational steps instead of re-showing owner creation.
  const currentStep: WizardStep = step ?? (data?.owner_exists ? 'emulators' : 'owner')

  async function completeSetup(target: string = '/') {
    setFinishing(true)
    setCompleteError(null)
    try {
      await apiFetch('/api/v1/settings/complete-first-run', { method: 'POST' })
      // Hard reload (not a client-side navigate) is deliberate: it forces
      // AppProvider's auth check and every route guard's first-run-status
      // query to refetch fresh instead of reading the now-stale cached
      // "incomplete" result, which would otherwise bounce back here.
      window.location.replace(target)
    } catch (err) {
      setCompleteError(err instanceof ApiError ? err.detail : 'Setup could not be completed.')
      setFinishing(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950 px-6 py-12">
      <div className="w-full max-w-2xl">
        {completeError && (
          <p role="alert" className="mb-4 text-sm text-[#ff6a55]">
            {completeError}
          </p>
        )}
        {currentStep === 'owner' && <Step0Owner onNext={() => setStep('emulators')} />}
        {currentStep === 'emulators' && (
          <StepEmulators
            emulators={data?.emulators ?? []}
            onNext={() => setStep('bios')}
            onSkip={() => completeSetup()}
            onFinishAndGoTo={completeSetup}
          />
        )}
        {currentStep === 'bios' && (
          <StepBios
            onBack={() => setStep('emulators')}
            onFinish={() => completeSetup()}
            onFinishAndGoTo={completeSetup}
            finishing={finishing}
          />
        )}
      </div>
    </main>
  )
}
