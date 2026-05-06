import { useState } from 'react'
import { apiFetch, ApiError } from '@/api/client'

interface Step4ProfileProps {
  onComplete: () => void
}

export default function Step4Profile({ onComplete }: Step4ProfileProps) {
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [nameError, setNameError] = useState<string | null>(null)
  const [pinError, setPinError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNameError(null)
    setPinError(null)

    if (!name.trim()) {
      setNameError('Display name is required.')
      return
    }
    if (pin && pin.length < 4) {
      setPinError('PIN must be at least 4 characters.')
      return
    }

    setSubmitting(true)
    try {
      await apiFetch('/api/v1/profiles/users/owner', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), pin: pin || null }),
      })
      await apiFetch('/api/v1/settings/complete-first-run', { method: 'POST' })
      onComplete()
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : 'Setup failed. Please try again.'
      setNameError(message)
      setSubmitting(false)
    }
  }

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Create Owner Profile
      </h2>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        This is the primary profile with full access. You can add sub-profiles
        later from the Profiles page.
      </p>

      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-5">
          <label
            htmlFor="owner-name"
            className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            Display name <span aria-hidden="true">*</span>
          </label>
          <input
            id="owner-name"
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              setNameError(null)
            }}
            required
            aria-describedby={nameError ? 'owner-name-error' : undefined}
            aria-invalid={nameError ? true : undefined}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
          />
          {nameError && (
            <p id="owner-name-error" role="alert" className="mt-1 text-xs text-[#ff6a55]">
              {nameError}
            </p>
          )}
        </div>

        <div className="mb-8">
          <label
            htmlFor="owner-pin"
            className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            PIN{' '}
            <span className="text-xs font-normal text-neutral-500 dark:text-neutral-400">
              (optional)
            </span>
          </label>
          <input
            id="owner-pin"
            type="password"
            value={pin}
            onChange={(e) => {
              setPin(e.target.value)
              setPinError(null)
            }}
            minLength={4}
            aria-describedby={pinError ? 'owner-pin-error' : 'owner-pin-hint'}
            aria-invalid={pinError ? true : undefined}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
          />
          <p id="owner-pin-hint" className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            Required when switching to this profile. Minimum 4 characters if set.
          </p>
          {pinError && (
            <p id="owner-pin-error" role="alert" className="mt-1 text-xs text-[#ff6a55]">
              {pinError}
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!name.trim() || submitting}
            className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
          >
            {submitting ? 'Setting up…' : 'Finish Setup'}
          </button>
        </div>
      </form>
    </section>
  )
}
