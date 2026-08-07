import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/api/client';
import { useAppContext } from '@/context/useAppContext';
import { Button, Modal, Input, FormField, Card, RadioGroup, Radio, Checkbox, Select } from '@/ui';

const FONT_SCALE_OPTIONS = [
  { value: '0.9', label: '90%' },
  { value: '1', label: '100% (default)' },
  { value: '1.1', label: '110%' },
  { value: '1.25', label: '125%' },
  { value: '1.5', label: '150%' },
];

function AppearanceSection() {
  const { state, dispatch } = useAppContext();

  return (
    <Card>
      <Card.Header>Appearance</Card.Header>
      <div className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Scales all text in the app. Useful on high resolution displays or for readability. Applies
          immediately and is remembered on this device.
        </p>
        <FormField label="Text size" htmlFor="font-scale">
          <Select
            id="font-scale"
            value={String(state.fontScale)}
            onValueChange={(v) => dispatch({ type: 'SET_FONT_SCALE', payload: parseFloat(v) })}
            options={FONT_SCALE_OPTIONS}
          />
        </FormField>
      </div>
    </Card>
  );
}

function MetadataProviderSection() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
  });

  const activeProvider = (settings?.metadata_provider as string | undefined) ?? 'thegamesdb';

  async function handleSelect(provider: 'thegamesdb' | 'igdb') {
    if (provider === activeProvider) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { metadata_provider: provider } }),
      });
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update metadata provider.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Card.Header>Metadata Provider</Card.Header>
      <div className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Which service "Fetch Metadata" searches. Only one provider is active at a time, switching
          providers below doesn't clear either one's saved credentials, it only changes which one is
          used.
        </p>
        <RadioGroup
          value={activeProvider}
          onValueChange={(v) => void handleSelect(v as 'thegamesdb' | 'igdb')}
          disabled={saving}
        >
          <Radio value="thegamesdb" label="TheGamesDB" />
          <Radio value="igdb" label="IGDB" />
        </RadioGroup>
        {activeProvider === 'thegamesdb' && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            Metadata fetched via this tool is powered by TheGamesDB.net.
          </p>
        )}
        {activeProvider === 'igdb' && (
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            Metadata fetched via this tool is powered by IGDB.com.
          </p>
        )}
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          Fetched metadata, including ratings, may be incomplete or inaccurate. If you rely on
          content filtering, verify ratings manually.
        </p>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {error}
          </p>
        )}
      </div>
    </Card>
  );
}

function TheGamesDbSection() {
  const { state: appState } = useAppContext();
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const { data: status } = useQuery<{ enabled: boolean }>({
    queryKey: ['thegamesdb-api-key-status'],
    queryFn: () => apiFetch('/api/v1/settings/thegamesdb-api-key/status'),
    enabled: !!appState.activeUser?.is_owner,
  });

  if (!appState.activeUser?.is_owner) return null;

  const enabled = status?.enabled ?? false;

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { THEGAMESDB_API_KEY: apiKey } }),
      });
      await queryClient.invalidateQueries({ queryKey: ['thegamesdb-api-key-status'] });
      setApiKey('');
      setSavedMsg('API key saved.');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save API key.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Card.Header>TheGamesDB</Card.Header>
      <div className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          API key for TheGamesDB metadata enrichment. Currently{' '}
          <strong>{enabled ? 'configured' : 'not configured'}</strong>. The key is never displayed
          after saving.{' '}
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
        <FormField label="API key" hint="Write-only, leave blank to keep the existing key.">
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
      </div>
    </Card>
  );
}

function IGDBSection() {
  const { state: appState } = useAppContext();
  const queryClient = useQueryClient();
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const { data: status } = useQuery<{ enabled: boolean }>({
    queryKey: ['igdb-status'],
    queryFn: () => apiFetch('/api/v1/settings/igdb-status'),
    enabled: !!appState.activeUser?.is_owner,
  });

  if (!appState.activeUser?.is_owner) return null;

  const enabled = status?.enabled ?? false;

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      // Each field is write-only and independent, only include a key here if
      // the user actually typed into it, so leaving one blank rotates only
      // the other rather than clearing both.
      const updates: Record<string, string> = {};
      if (clientId) updates.IGDB_CLIENT_ID = clientId;
      if (clientSecret) updates.IGDB_CLIENT_SECRET = clientSecret;
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates }),
      });
      await queryClient.invalidateQueries({ queryKey: ['igdb-status'] });
      setClientId('');
      setClientSecret('');
      setSavedMsg('IGDB credentials saved.');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save IGDB credentials.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Card.Header>IGDB</Card.Header>
      <div className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Twitch Developer app credentials for IGDB metadata enrichment. Currently{' '}
          <strong>{enabled ? 'configured' : 'not configured'}</strong>. Neither value is displayed
          after saving.{' '}
          <a
            href="https://dev.twitch.tv/console/apps"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            Register a Twitch app
          </a>{' '}
          ·{' '}
          <a
            href="https://api-docs.igdb.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            IGDB API docs
          </a>
        </p>
        <FormField label="Client ID" hint="Write-only, leave blank to keep the existing value.">
          <Input
            type="password"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            autoComplete="off"
            placeholder={enabled ? '••••••••' : 'Paste client ID here'}
          />
        </FormField>
        <FormField
          label="Client secret"
          hint="Write-only, leave blank to keep the existing value."
        >
          <Input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            autoComplete="off"
            placeholder={enabled ? '••••••••' : 'Paste client secret here'}
          />
        </FormField>
        <div>
          <Button
            size="sm"
            loading={saving}
            onClick={handleSave}
            disabled={!clientId && !clientSecret}
          >
            Save
          </Button>
        </div>
        {savedMsg && <p className="text-sm text-green-600 dark:text-green-400">{savedMsg}</p>}
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {error}
          </p>
        )}
      </div>
    </Card>
  );
}

function PinPepperSection() {
  const { state: appState } = useAppContext();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [pepper, setPepper] = useState('');
  const [ownerPin, setOwnerPin] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const { data: status } = useQuery<{ enabled: boolean }>({
    queryKey: ['pin-pepper-status'],
    queryFn: () => apiFetch('/api/v1/settings/pin-pepper/status'),
    enabled: !!appState.activeUser?.is_owner,
  });

  if (!appState.activeUser?.is_owner) return null;

  const enabled = status?.enabled ?? false;

  function openModal() {
    setPepper('');
    setOwnerPin('');
    setError(null);
    setResult(null);
    setModalOpen(true);
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<{
        pepper_enabled: boolean;
        owner_rehashed: boolean;
        sub_accounts_reset: string[];
      }>('/api/v1/settings/pin-pepper', {
        method: 'PATCH',
        body: JSON.stringify({ pepper, owner_pin: ownerPin || null }),
      });
      await queryClient.invalidateQueries({ queryKey: ['pin-pepper-status'] });
      setResult(
        res.sub_accounts_reset.length > 0
          ? `Done. ${res.sub_accounts_reset.join(', ')} must set a new PIN before next login.`
          : 'Done.',
      );
      setModalOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update pepper.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <Card.Header>PIN Pepper</Card.Header>
      <div className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Optional app-level secret mixed into every PIN hash. Currently{' '}
          <strong>{enabled ? 'enabled' : 'disabled'}</strong>. Changing this invalidates every
          existing PIN, sub-accounts will need their PIN reset by an admin, and you'll re-set your
          own PIN here using your current one.
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
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setModalOpen(false)}
                disabled={submitting}
              >
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
          <FormField
            label="Your current owner PIN"
            hint="Required to re-hash your own PIN under the new pepper."
          >
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
      </div>
    </Card>
  );
}

const RETENTION_OPTIONS: { value: 'never' | '1_week' | '1_month' | '6_months'; label: string }[] = [
  { value: 'never', label: 'Keep forever' },
  { value: '1_week', label: '1 week' },
  { value: '1_month', label: '1 month' },
  { value: '6_months', label: '6 months' },
];

function LaunchHistoryRetentionSection() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
  });

  const active = (settings?.launch_history_retention as string | undefined) ?? 'never';

  async function handleSelect(value: string) {
    if (value === active) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { launch_history_retention: value } }),
      });
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update retention.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Card.Header>Launch History Retention</Card.Header>
      <div className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          How long launch session history is kept. Older records are deleted automatically. "Keep
          forever" preserves everything. This runs in the background and does not affect launches.
        </p>
        <RadioGroup value={active} onValueChange={handleSelect} disabled={saving}>
          {RETENTION_OPTIONS.map((opt) => (
            <Radio key={opt.value} value={opt.value} label={opt.label} />
          ))}
        </RadioGroup>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {error}
          </p>
        )}
      </div>
    </Card>
  );
}

function DeleteOriginalOnUploadSection() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
  });

  const enabled = Boolean(settings?.delete_original_on_upload);

  async function handleToggle(next: boolean) {
    setSaving(true);
    setError(null);
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { delete_original_on_upload: next } }),
      });
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update setting.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Card.Header>Server Path Import</Card.Header>
      <div className="space-y-3">
        <Checkbox
          checked={enabled}
          onCheckedChange={handleToggle}
          disabled={saving}
          label='Delete the original file/folder after importing via "Browse Server Files…"'
        />
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Default for the "delete once uploaded" checkbox when adding media by browsing a path
          already on this server. Only applies to that input method, items dragged or dropped
          through the browser can never delete their source, since the browser never exposes its
          real file path. This cannot be undone.
        </p>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {error}
          </p>
        )}
      </div>
    </Card>
  );
}

function DeleteMediaOnRemovalSection() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: settings } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/api/v1/settings'),
  });

  const enabled = Boolean(settings?.delete_media_on_removal);

  async function handleToggle(next: boolean) {
    setSaving(true);
    setError(null);
    try {
      await apiFetch('/api/v1/settings', {
        method: 'PATCH',
        body: JSON.stringify({ updates: { delete_media_on_removal: next } }),
      });
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update setting.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Card.Header>Library Removal</Card.Header>
      <div className="space-y-3">
        <Checkbox
          checked={enabled}
          onCheckedChange={handleToggle}
          disabled={saving}
          label="Permanently delete media files when removing from library"
        />
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          When enabled, removing an item from the library also deletes its media files from disk.
          This cannot be undone.
        </p>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            ❌ {error}
          </p>
        )}
      </div>
    </Card>
  );
}

export default function AdvancedTab() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetSuccess, setResetSuccess] = useState(false);

  async function handleReset() {
    setResetting(true);
    setResetError(null);
    setResetSuccess(false);
    try {
      const { token } = await apiFetch<{ token: string }>(
        '/api/v1/emulator-items/sandbox-state/confirm-token',
      );
      await apiFetch('/api/v1/emulator-items/sandbox-state', {
        method: 'DELETE',
        body: JSON.stringify({ confirmation_token: token }),
      });
      setResetSuccess(true);
    } catch (err) {
      setResetError(err instanceof ApiError ? err.detail : 'Reset failed.');
    } finally {
      setResetting(false);
      setConfirmOpen(false);
    }
  }

  return (
    <div className="mt-6 space-y-6">
      <AppearanceSection />
      <MetadataProviderSection />
      <TheGamesDbSection />
      <IGDBSection />
      <PinPepperSection />
      <DeleteMediaOnRemovalSection />
      <DeleteOriginalOnUploadSection />
      <LaunchHistoryRetentionSection />

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
  );
}
