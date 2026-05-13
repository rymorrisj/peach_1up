import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock, Unlock, Trash2, KeyRound } from 'lucide-react'
import { apiFetch, ApiError } from '@/api/client'
import { useAppContext } from '@/context/AppContext'
import { PageHeader, FormField, Button, Input, Modal } from '@/ui'
import LoadingSpinner from '@/components/common/LoadingSpinner'
import PathInput from '@/components/common/PathInput'
import UserSwitcher from '@/components/UserSwitcher'
import { cn } from '@/lib/utils'
import { RATING_OPTIONS as BASE_RATING_OPTIONS } from '@/generated/constants'
import type { components } from '@shared/types'
type User = components['schemas']['UserRead']

// ─── Library paths section ───────────────────────────────────────────────────

type LibraryKey = 'images_path' | 'profiles_path' | 'rom_path'

interface PathFieldState {
  value: string
  saving: boolean
  saved: boolean
  error: string | null
}

const PATH_ENTRIES: { key: LibraryKey; settingsKey: string; label: string; hint: string }[] = [
  {
    key: 'images_path',
    settingsKey: 'IMAGES_PATH',
    label: 'Images Path',
    hint: 'Directory where OS images and game media are stored',
  },
  {
    key: 'profiles_path',
    settingsKey: 'PROFILES_PATH',
    label: 'Profiles Path',
    hint: 'Directory where game profiles are saved',
  },
  {
    key: 'rom_path',
    settingsKey: 'ROM_PATH',
    label: 'ROM Path',
    hint: '86Box ROM pack directory — required for accuracy mode',
  },
]

const EMPTY_FIELD: PathFieldState = { value: '', saving: false, saved: false, error: null }

// ─── Users section ───────────────────────────────────────────────────────────

const PERMISSION_FLAGS: { key: keyof User; label: string }[] = [
  { key: 'can_launch_media', label: 'Launch media' },
  { key: 'can_edit_library', label: 'Edit library' },
  { key: 'can_edit_platforms', label: 'Edit platforms' },
  { key: 'can_manage_profiles', label: 'Manage profiles' },
  { key: 'can_edit_settings', label: 'Edit settings' },
  { key: 'is_admin', label: 'Admin' },
]

const RATING_OPTIONS = [{ value: '', label: 'No restriction' }, ...BASE_RATING_OPTIONS.slice(1)]

interface AddUserForm {
  name: string
  pin: string
  can_launch_media: boolean
  can_edit_library: boolean
  can_edit_platforms: boolean
  can_manage_profiles: boolean
  can_edit_settings: boolean
  is_admin: boolean
  max_content_rating: string
  block_unrated_media: boolean
}

const EMPTY_ADD_FORM: AddUserForm = {
  name: '',
  pin: '',
  can_launch_media: true,
  can_edit_library: false,
  can_edit_platforms: false,
  can_manage_profiles: false,
  can_edit_settings: false,
  is_admin: false,
  max_content_rating: '',
  block_unrated_media: false,
}

type ResetPinTarget = { user: User; pin: string; error: string | null; submitting: boolean }
type ActionState = { userId: number; action: 'unlock' | 'delete'; submitting: boolean } | null

const SELECT_CLASS =
  'w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100'

function Toggle({ checked, onChange, id }: { checked: boolean; onChange: (v: boolean) => void; id: string }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#ff8a5c] focus:ring-offset-2',
        checked ? 'bg-[#ff8a5c]' : 'bg-neutral-300 dark:bg-neutral-600',
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-[1.125rem]' : 'translate-x-[0.1875rem]',
        )}
      />
    </button>
  )
}

function permissionSummary(user: User): string {
  const labels: string[] = []
  if (user.can_launch_media) labels.push('launch')
  if (user.can_edit_library) labels.push('library')
  if (user.can_edit_platforms) labels.push('platforms')
  if (user.can_manage_profiles) labels.push('profiles')
  if (user.can_edit_settings) labels.push('settings')
  if (user.is_admin) labels.push('admin')
  return labels.length ? labels.join(', ') : 'no permissions'
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Settings() {
  const { state: appState } = useAppContext()
  const queryClient = useQueryClient()
  const isAdmin = appState.activeUser?.is_admin ?? false

  // ── Library paths ──
  const { data: settings, isLoading: settingsLoading } = useQuery<Record<string, string | null>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch<Record<string, string | null>>('/api/v1/settings'),
  })

  const [fields, setFields] = useState<Record<LibraryKey, PathFieldState>>({
    images_path: EMPTY_FIELD,
    profiles_path: EMPTY_FIELD,
    rom_path: EMPTY_FIELD,
  })
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (!settings || initialized) return
    setFields({
      images_path: { ...EMPTY_FIELD, value: settings['IMAGES_PATH'] ?? '' },
      profiles_path: { ...EMPTY_FIELD, value: settings['PROFILES_PATH'] ?? '' },
      rom_path: { ...EMPTY_FIELD, value: settings['ROM_PATH'] ?? '' },
    })
    setInitialized(true)
  }, [settings, initialized])

  function setField(key: LibraryKey, patch: Partial<PathFieldState>) {
    setFields((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }))
  }

  async function handleSave(key: LibraryKey) {
    const path = fields[key].value.trim()
    if (!path) return
    setField(key, { saving: true, error: null, saved: false })
    try {
      await apiFetch('/api/v1/settings/library-path', {
        method: 'POST',
        body: JSON.stringify({ key, path }),
      })
      setField(key, { saving: false, saved: true })
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Failed to save.'
      setField(key, { saving: false, error: msg })
    }
  }

  // ── Users ──
  const { data: users, isLoading: usersLoading } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/users'),
    enabled: isAdmin,
  })

  const [addOpen, setAddOpen] = useState(false)
  const [addForm, setAddForm] = useState<AddUserForm>(EMPTY_ADD_FORM)
  const [addErrors, setAddErrors] = useState<Partial<Record<keyof AddUserForm, string>>>({})
  const [addSubmitting, setAddSubmitting] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const [resetPinTarget, setResetPinTarget] = useState<ResetPinTarget | null>(null)
  const [actionState, setActionState] = useState<ActionState>(null)

  function setAddField<K extends keyof AddUserForm>(key: K, value: AddUserForm[K]) {
    setAddForm((prev) => ({ ...prev, [key]: value }))
    setAddErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  function validateAdd(): boolean {
    const errors: Partial<Record<keyof AddUserForm, string>> = {}
    if (!addForm.name.trim()) errors.name = 'Name is required.'
    if (addForm.pin && !/^\d{4,6}$/.test(addForm.pin)) errors.pin = 'PIN must be 4–6 digits.'
    setAddErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleAddUser() {
    if (!validateAdd()) return
    setAddSubmitting(true)
    setAddError(null)
    try {
      await apiFetch('/api/v1/users', {
        method: 'POST',
        body: JSON.stringify({
          name: addForm.name.trim(),
          pin: addForm.pin || undefined,
          can_launch_media: addForm.can_launch_media,
          can_edit_library: addForm.can_edit_library,
          can_edit_platforms: addForm.can_edit_platforms,
          can_manage_profiles: addForm.can_manage_profiles,
          can_edit_settings: addForm.can_edit_settings,
          is_admin: addForm.is_admin,
          max_content_rating: addForm.max_content_rating || null,
          block_unrated_media: addForm.block_unrated_media,
        }),
      })
      await queryClient.invalidateQueries({ queryKey: ['users'] })
      setAddOpen(false)
      setAddForm(EMPTY_ADD_FORM)
    } catch (err) {
      setAddError(err instanceof ApiError ? err.detail : 'Failed to create user.')
    } finally {
      setAddSubmitting(false)
    }
  }

  async function handleResetPin() {
    if (!resetPinTarget || resetPinTarget.submitting) return
    if (!/^\d{4,6}$/.test(resetPinTarget.pin)) {
      setResetPinTarget((p) => p && { ...p, error: 'PIN must be 4–6 digits.' })
      return
    }
    setResetPinTarget((p) => p && { ...p, submitting: true, error: null })
    try {
      await apiFetch(`/api/v1/users/${resetPinTarget.user.id}/reset-pin`, {
        method: 'POST',
        body: JSON.stringify({ pin: resetPinTarget.pin }),
      })
      await queryClient.invalidateQueries({ queryKey: ['users'] })
      setResetPinTarget(null)
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Failed to reset PIN.'
      setResetPinTarget((p) => p && { ...p, submitting: false, error: msg })
    }
  }

  async function handleUnlock(user: User) {
    setActionState({ userId: user.id, action: 'unlock', submitting: true })
    try {
      await apiFetch(`/api/v1/users/${user.id}/unlock`, { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    } catch {
      // error silently — list will not change
    } finally {
      setActionState(null)
    }
  }

  async function handleDelete(user: User) {
    if (!confirm(`Delete account "${user.name}"? This cannot be undone.`)) return
    setActionState({ userId: user.id, action: 'delete', submitting: true })
    try {
      await apiFetch(`/api/v1/users/${user.id}`, { method: 'DELETE' })
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    } catch {
      // error silently
    } finally {
      setActionState(null)
    }
  }

  return (
    <>
      <PageHeader title="Settings" description="Configure library paths and application settings." />

      {settingsLoading ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
          <LoadingSpinner label="Loading settings…" />
          <span aria-hidden="true">Loading settings…</span>
        </div>
      ) : (
        <div className="max-w-xl space-y-10">

          {/* ── Library Paths ── */}
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              Library Paths
            </h2>
            <div className="mt-4 space-y-5">
              {PATH_ENTRIES.map(({ key, label, hint }) => (
                <FormField
                  key={key}
                  label={label}
                  htmlFor={`path-${key}`}
                  hint={hint}
                  error={fields[key].error ?? undefined}
                >
                  <div className="mt-1 flex gap-2">
                    <PathInput
                      id={`path-${key}`}
                      mode="folder"
                      value={fields[key].value}
                      onChange={(v) => setField(key, { value: v, saved: false })}
                      placeholder={`/path/to/${key.replace('_path', '').replace('_', '-')}`}
                      hasError={!!fields[key].error}
                      className="flex-1 min-w-0"
                    />
                    <Button
                      variant="secondary"
                      onClick={() => handleSave(key)}
                      disabled={!fields[key].value.trim() || fields[key].saving}
                      loading={fields[key].saving}
                    >
                      {fields[key].saved ? 'Saved ✓' : 'Save'}
                    </Button>
                  </div>
                </FormField>
              ))}
            </div>
          </section>

          {/* ── Account Switcher ── */}
          <UserSwitcher />

          {/* ── Users (admin only) ── */}
          {isAdmin && (
            <section>
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                  Users
                </h2>
                <Button size="sm" onClick={() => { setAddForm(EMPTY_ADD_FORM); setAddError(null); setAddErrors({}); setAddOpen(true) }}>
                  + Add Account
                </Button>
              </div>

              {usersLoading ? (
                <div className="mt-4 flex items-center gap-2 text-sm text-neutral-500">
                  <LoadingSpinner label="Loading users…" />
                  <span aria-hidden="true">Loading users…</span>
                </div>
              ) : (
                <ul role="list" className="mt-4 divide-y divide-neutral-200 dark:divide-neutral-800">
                  {(users ?? []).map((user) => {
                    const isBusy = actionState?.userId === user.id && actionState.submitting
                    return (
                      <li key={user.id} className="py-3">
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-neutral-900 dark:text-neutral-100">
                                {user.name}
                              </span>
                              {user.is_owner && (
                                <span className="rounded-full bg-peach/15 px-2 py-0.5 text-xs font-medium text-peach">
                                  owner
                                </span>
                              )}
                              {user.is_locked && (
                                <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-600 dark:bg-red-900/30 dark:text-red-400">
                                  <Lock size={10} />
                                  locked
                                </span>
                              )}
                            </div>
                            <p className="mt-0.5 truncate text-xs text-neutral-400 dark:text-neutral-500">
                              {permissionSummary(user)}
                              {user.max_content_rating && ` · max ${user.max_content_rating}`}
                              {user.block_unrated_media && ' · block unrated'}
                            </p>
                          </div>

                          {!user.is_owner && (
                            <div className="flex shrink-0 items-center gap-1.5">
                              <Button
                                variant="ghost"
                                size="sm"
                                title="Reset PIN"
                                disabled={isBusy}
                                onClick={() => setResetPinTarget({ user, pin: '', error: null, submitting: false })}
                              >
                                <KeyRound size={14} />
                              </Button>
                              {user.is_locked && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  title="Unlock account"
                                  disabled={isBusy}
                                  loading={actionState?.userId === user.id && actionState.action === 'unlock' && actionState.submitting}
                                  onClick={() => handleUnlock(user)}
                                >
                                  <Unlock size={14} />
                                </Button>
                              )}
                              <Button
                                variant="destructive"
                                size="sm"
                                title="Delete account"
                                disabled={isBusy}
                                onClick={() => handleDelete(user)}
                              >
                                <Trash2 size={14} />
                              </Button>
                            </div>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>
          )}
        </div>
      )}

      {/* ── Add Account Modal ── */}
      <Modal
        open={addOpen}
        title="Add Account"
        onClose={() => setAddOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)} disabled={addSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleAddUser} loading={addSubmitting}>
              Create Account
            </Button>
          </>
        }
      >
        <FormField label="Name" htmlFor="add-name" required error={addErrors.name}>
          <Input
            id="add-name"
            value={addForm.name}
            onChange={(e) => setAddField('name', e.target.value)}
            placeholder="Alex"
            hasError={!!addErrors.name}
          />
        </FormField>

        <FormField
          label="PIN"
          htmlFor="add-pin"
          hint="4–6 digits. Leave blank for no PIN."
          error={addErrors.pin}
        >
          <Input
            id="add-pin"
            type="password"
            inputMode="numeric"
            maxLength={6}
            value={addForm.pin}
            onChange={(e) => setAddField('pin', e.target.value.replace(/\D/g, ''))}
            placeholder="••••"
            hasError={!!addErrors.pin}
          />
        </FormField>

        <fieldset>
          <legend className="mb-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
            Permissions
          </legend>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            {PERMISSION_FLAGS.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
                <input
                  type="checkbox"
                  checked={addForm[key] as boolean}
                  onChange={(e) => setAddField(key as keyof AddUserForm, e.target.checked as never)}
                  className="h-4 w-4 rounded border-neutral-300 text-[#ff8a5c] focus:ring-[#ff8a5c] dark:border-neutral-600"
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>

        <FormField label="Max Content Rating" htmlFor="add-rating">
          <select
            id="add-rating"
            value={addForm.max_content_rating}
            onChange={(e) => setAddField('max_content_rating', e.target.value)}
            className={SELECT_CLASS}
          >
            {RATING_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </FormField>

        <FormField label="Block unrated media" htmlFor="add-block-unrated">
          <div className="mt-1 flex items-center gap-3">
            <Toggle
              id="add-block-unrated"
              checked={addForm.block_unrated_media}
              onChange={(v) => setAddField('block_unrated_media', v)}
            />
            <span className="text-sm text-neutral-600 dark:text-neutral-300">
              {addForm.block_unrated_media ? 'Yes — hide items with no rating' : 'No'}
            </span>
          </div>
        </FormField>

        {addError && (
          <p role="alert" className="text-sm text-red-500 dark:text-red-400">
            ❌ {addError}
          </p>
        )}
      </Modal>

      {/* ── Reset PIN Modal ── */}
      {resetPinTarget && (
        <Modal
          open
          title={`Reset PIN — ${resetPinTarget.user.name}`}
          onClose={() => setResetPinTarget(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setResetPinTarget(null)} disabled={resetPinTarget.submitting}>
                Cancel
              </Button>
              <Button onClick={handleResetPin} loading={resetPinTarget.submitting}>
                Set PIN
              </Button>
            </>
          }
        >
          <FormField
            label="New PIN"
            htmlFor="reset-pin"
            hint="4–6 digits."
            error={resetPinTarget.error ?? undefined}
          >
            <Input
              id="reset-pin"
              type="password"
              inputMode="numeric"
              maxLength={6}
              autoFocus
              value={resetPinTarget.pin}
              onChange={(e) =>
                setResetPinTarget((p) => p && { ...p, pin: e.target.value.replace(/\D/g, ''), error: null })
              }
              placeholder="••••"
              hasError={!!resetPinTarget.error}
              className="text-center tracking-[0.5em] text-lg"
            />
          </FormField>
        </Modal>
      )}
    </>
  )
}
