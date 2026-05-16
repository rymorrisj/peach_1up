import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { apiFetch } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import Step0Owner from './Step0Owner'
import Step1Welcome from './Step1Welcome'
import Step2Emulators from './Step2Emulators'
import Step3Paths from './Step3Paths'
import Step4Profile from './Step4Profile'
import type { FirstRunStatus } from './types'

type MainStep = 1 | 2 | 3 | 4

export default function FirstRun() {
  const [ownerDone, setOwnerDone] = useState(false)
  const [step, setStep] = useState<MainStep>(1)
  const { data, isLoading } = useQuery({
    queryKey: ['first-run-status'],
    queryFn: () => apiFetch<FirstRunStatus>('/api/v1/settings/first-run-status'),
  })

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950">
        <LoadingSpinner label="Checking setup status…" />
      </main>
    )
  }

  if (data?.first_run_complete) return <Navigate to="/library" replace />

  const needsOwnerSetup = data !== undefined && !data.owner_exists
  const showOwnerStep = needsOwnerSetup && !ownerDone
  const totalSteps = needsOwnerSetup ? 5 : 4
  const currentStep = showOwnerStep ? 1 : (needsOwnerSetup ? step + 1 : step)

  return (
    <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950 px-6 py-12">
      <div className="w-full max-w-2xl">
        <div
          className="mb-1 text-right text-xs text-neutral-500 dark:text-neutral-500"
          aria-hidden="true"
        >
          Step {currentStep} of {totalSteps}
        </div>
        <div
          role="progressbar"
          aria-valuenow={currentStep}
          aria-valuemin={1}
          aria-valuemax={totalSteps}
          aria-label="Setup progress"
          className="mb-8 h-px rounded-full bg-neutral-200 dark:bg-neutral-800"
        >
          <div
            className="h-full rounded-full bg-[#ff8a5c] transition-all duration-300"
            style={{ width: `${(currentStep / totalSteps) * 100}%` }}
          />
        </div>

        {showOwnerStep && <Step0Owner onNext={() => setOwnerDone(true)} />}
        {!showOwnerStep && step === 1 && <Step1Welcome onNext={() => setStep(2)} />}
        {!showOwnerStep && step === 2 && data && <Step2Emulators status={data} onNext={() => setStep(3)} />}
        {!showOwnerStep && step === 3 && data && <Step3Paths status={data} onNext={() => setStep(4)} />}
        {!showOwnerStep && step === 4 && <Step4Profile />}
      </div>
    </main>
  )
}
