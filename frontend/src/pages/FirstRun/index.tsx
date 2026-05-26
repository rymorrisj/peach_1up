import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { apiFetch, ApiError } from '@/api/client'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import Step0Owner from './Step0Owner'
import type { FirstRunStatus } from './types'

export default function FirstRun() {
  const [completeError, setCompleteError] = useState<string | null>(null)
  const [finishing, setFinishing] = useState(false)
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

  if (data?.first_run_complete) return <Navigate to="/library" replace />

  async function completeSetup() {
    setFinishing(true)
    setCompleteError(null)
    try {
      await apiFetch('/api/v1/settings/complete-first-run', { method: 'POST' })
      window.location.replace('/')
    } catch (err) {
      setCompleteError(err instanceof ApiError ? err.detail : 'Setup could not be completed.')
      setFinishing(false)
    }
  }

  // Owner already exists but first_run not yet flagged — just finish it
  if (data?.owner_exists) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950 px-6 py-12">
        <div className="w-full max-w-2xl">
          <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            Setup Complete
          </h2>
          <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
            Your account is ready.
          </p>
          {completeError && (
            <p role="alert" className="mb-4 text-sm text-[#ff6a55]">
              {completeError}
            </p>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={completeSetup}
              className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
            >
              Continue
            </button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-white dark:bg-surface-950 px-6 py-12">
      <div className="w-full max-w-2xl">
        {completeError && (
          <p role="alert" className="mb-4 text-sm text-[#ff6a55]">
            {completeError}
          </p>
        )}
        <Step0Owner onNext={completeSetup} />
      </div>
    </main>
  )
}
