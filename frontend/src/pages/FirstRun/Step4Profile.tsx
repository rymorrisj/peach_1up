import { useState } from 'react'
import { apiFetch, ApiError } from '@/api/client'

export default function Step4Profile() {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleComplete() {
    setSubmitting(true)
    setError(null)
    try {
      await apiFetch('/api/v1/settings/complete-first-run', { method: 'POST' })
      window.location.replace('/')
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Setup failed. Please try again.'
      setError(message)
      setSubmitting(false)
    }
  }

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        You're all set
      </h2>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        Your library is ready. Add media and assign launch profiles from the Library page.
      </p>

      {error && (
        <p role="alert" className="mb-4 text-sm text-[#ff6a55]">
          {error}
        </p>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          disabled={submitting}
          onClick={handleComplete}
          className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
        >
          {submitting ? 'Setting up…' : 'Finish Setup'}
        </button>
      </div>
    </section>
  )
}
