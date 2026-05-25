import { useState } from 'react'
import { apiFetch, ApiError } from '@/api/client'
import { Button, Modal } from '@/ui'

export default function AdvancedTab() {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetSuccess, setResetSuccess] = useState(false)

  async function handleReset() {
    setResetting(true)
    setResetError(null)
    setResetSuccess(false)
    try {
      const { token } = await apiFetch<{ token: string }>(
        '/api/v1/emulators/sandbox-state/confirm-token',
      )
      await apiFetch('/api/v1/emulators/sandbox-state', {
        method: 'DELETE',
        body: JSON.stringify({ confirmation_token: token }),
      })
      setResetSuccess(true)
    } catch (err) {
      setResetError(err instanceof ApiError ? err.detail : 'Reset failed.')
    } finally {
      setResetting(false)
      setConfirmOpen(false)
    }
  }

  return (
    <div className="mt-6 space-y-6">
      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
          Sandbox
        </h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Remove all AppContainer profiles created by Peach 1UP. Profiles are recreated
          automatically on next launch.
        </p>
        <div>
          <Button variant="secondary" size="sm" onClick={() => setConfirmOpen(true)}>
            Reset sandbox state
          </Button>
        </div>
        {resetSuccess && (
          <p className="text-sm text-green-600 dark:text-green-400">Sandbox state reset.</p>
        )}
        {resetError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {resetError}
          </p>
        )}
      </section>

      <Modal
        open={confirmOpen}
        title="Reset sandbox state"
        onClose={() => setConfirmOpen(false)}
        footer={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setConfirmOpen(false)}
              disabled={resetting}
            >
              Cancel
            </Button>
            <Button size="sm" loading={resetting} onClick={handleReset}>
              Reset
            </Button>
          </>
        }
      >
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          This will delete all AppContainer profiles and they will be recreated on next launch.
          Active emulator sessions will not be affected.
        </p>
      </Modal>
    </div>
  )
}
