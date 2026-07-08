import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import { useAppContext } from '@/context/useAppContext'
import { Button, Modal, Input, FormField } from '@/ui'

function TheGamesDbSection() {
  const { state: appState } = useAppContext()
  const queryClient = useQueryClient()
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)

  const { data: status } = useQuery<{ enabled: boolean }>({
    queryKey: ['thegamesdb-api-key-status'],
    queryFn: () => apiFetch('/api/v1/settings/thegamesdb-api-key/status'),
    enabled: !!appState.activeUser?.is_owner,
  })

  if (!appState.activeUser?.is_owner) return null

  const enabled = status?.enabled ?? false

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSavedMsg(null)
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { THEGAMESDB_API_KEY: apiKey } }),
      })
      await queryClient.invalidateQueries({ queryKey: ['thegamesdb-api-key-status'] })
      setApiKey('')
      setSavedMsg('API key saved.')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save API key.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        TheGamesDB
      </h2>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        API key for TheGamesDB metadata enrichment. Currently{' '}
        <strong>{enabled ? 'configured' : 'not configured'}</strong>. The key is never
        displayed after saving.{' '}
        <a
          href="https://api.thegamesdb.net/key.php"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          Request an API key
        </a>{' '}
        ·{' '}
        <a
          href="https://api.thegamesdb.net/key.php"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          View your account &amp; allowance
        </a>
        . Each metadata fetch uses approximately 2–3 API requests.
      </p>
      <FormField label="API key" hint="Write-only — leave blank to keep the existing key.">
        <Input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="off"
          placeholder={enabled ? '••••••••' : 'Paste key here'}
        />
      </FormField>
      <div>
        <Button size="sm" loading={saving} onClick={handleSave} disabled={!apiKey}>
          Save
        </Button>
      </div>
      {savedMsg && <p className="text-sm text-green-600 dark:text-green-400">{savedMsg}</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </section>
  )
}

function PinPepperSection() {
  const { state: appState } = useAppContext()
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [pepper, setPepper] = useState('')
  const [ownerPin, setOwnerPin] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)

  const { data: status } = useQuery<{ enabled: boolean }>({
    queryKey: ['pin-pepper-status'],
    queryFn: () => apiFetch('/api/v1/settings/pin-pepper/status'),
    enabled: !!appState.activeUser?.is_owner,
  })

  if (!appState.activeUser?.is_owner) return null

  const enabled = status?.enabled ?? false

  function openModal() {
    setPepper('')
    setOwnerPin('')
    setError(null)
    setResult(null)
    setModalOpen(true)
  }

  async function handleSubmit() {
    setSubmitting(true)
    setError(null)
    try {
      const res = await apiFetch<{
        pepper_enabled: boolean
        owner_rehashed: boolean
        sub_accounts_reset: string[]
      }>('/api/v1/settings/pin-pepper', {
        method: 'PATCH',
        body: JSON.stringify({ pepper, owner_pin: ownerPin || null }),
      })
      await queryClient.invalidateQueries({ queryKey: ['pin-pepper-status'] })
      setResult(
        res.sub_accounts_reset.length > 0
          ? `Done. ${res.sub_accounts_reset.join(', ')} must set a new PIN before next login.`
          : 'Done.',
      )
      setModalOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update pepper.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        PIN Pepper
      </h2>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        Optional app-level secret mixed into every PIN hash. Currently{' '}
        <strong>{enabled ? 'enabled' : 'disabled'}</strong>. Changing this invalidates every
        existing PIN — sub-accounts will need their PIN reset by an admin, and you'll re-set
        your own PIN here using your current one.
      </p>
      <div>
        <Button variant="secondary" size="sm" onClick={openModal}>
          {enabled ? 'Rotate or disable pepper' : 'Enable pepper'}
        </Button>
      </div>
      {result && <p className="text-sm text-green-600 dark:text-green-400">{result}</p>}

      <Modal
        open={modalOpen}
        title="Change PIN pepper"
        onClose={() => setModalOpen(false)}
        busy={submitting}
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setModalOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button size="sm" loading={submitting} onClick={handleSubmit}>
              Save
            </Button>
          </>
        }
      >
        <FormField label="New pepper value" hint="Leave blank to disable the pepper.">
          <Input
            type="password"
            value={pepper}
            onChange={(e) => setPepper(e.target.value)}
            autoComplete="off"
          />
        </FormField>
        <FormField label="Your current owner PIN" hint="Required to re-hash your own PIN under the new pepper.">
          <Input
            type="password"
            value={ownerPin}
            onChange={(e) => setOwnerPin(e.target.value)}
            autoComplete="off"
          />
        </FormField>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {error}
          </p>
        )}
      </Modal>
    </section>
  )
}

function DeleteOriginalOnUploadSection() {
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
  })

  const enabled = Boolean(settings?.delete_original_on_upload)

  async function handleToggle(next: boolean) {
    setSaving(true)
    setError(null)
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { delete_original_on_upload: next } }),
      })
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update setting.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Server Path Import
      </h2>
      <label className="flex items-center gap-3">
        <input
          type="checkbox"
          checked={enabled}
          disabled={saving}
          onChange={(e) => handleToggle(e.target.checked)}
          className="h-4 w-4 shrink-0 accent-[#ff8a5c]"
        />
        <span className="text-sm text-neutral-900 dark:text-neutral-100">
          Delete the original file/folder after importing via "Browse Server Files…"
        </span>
      </label>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        Default for the "delete once uploaded" checkbox when adding media by browsing a path
        already on this server. Only applies to that input method — items dragged or dropped
        through the browser can never delete their source, since the browser never exposes its
        real file path. This cannot be undone.
      </p>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </section>
  )
}

function DeleteMediaOnRemovalSection() {
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
  })

  const enabled = Boolean(settings?.delete_media_on_removal)

  async function handleToggle(next: boolean) {
    setSaving(true)
    setError(null)
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { delete_media_on_removal: next } }),
      })
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update setting.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Library Removal
      </h2>
      <label className="flex items-center gap-3">
        <input
          type="checkbox"
          checked={enabled}
          disabled={saving}
          onChange={(e) => handleToggle(e.target.checked)}
          className="h-4 w-4 shrink-0 accent-[#ff8a5c]"
        />
        <span className="text-sm text-neutral-900 dark:text-neutral-100">
          Permanently delete media files when removing from library
        </span>
      </label>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        When enabled, removing an item from the library also deletes its media files from disk.
        This cannot be undone.
      </p>
      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </section>
  )
}

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
      <TheGamesDbSection />
      <PinPepperSection />
      <DeleteMediaOnRemovalSection />
      <DeleteOriginalOnUploadSection />

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
        busy={resetting}
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
