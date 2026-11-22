import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError, TimeoutError } from '@/api/client';
import { LAUNCH_TIMEOUT_MS } from '@/hooks/useLaunch';
import TopBar from '@/components/layout/TopBar';
import { PLATFORM_LABELS } from '@/generated/constants';
import { PLATFORM_COLOR } from '@/types/platform';
import { useToast } from '@/ui/ToastProvider';
import type { components } from '@shared/types';

type Environment = components['schemas']['EnvironmentItemRead'];

type Tab = 'overview' | 'notes';

function TabBtn({
  label,
  active,
  onClick,
  count,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '10px 14px',
        border: 0,
        background: 'transparent',
        borderBottom: active ? '2px solid rgb(var(--peach-500))' : '2px solid transparent',
        color: active ? 'rgb(var(--fg-1))' : 'rgb(var(--fg-3))',
        fontFamily: 'var(--font-display)',
        fontWeight: 600,
        fontSize: '0.8125rem',
        lineHeight: 1,
        cursor: 'pointer',
        marginBottom: -1,
      }}
    >
      {label}
      {count != null && (
        <span style={{ opacity: 0.55, marginLeft: 6, fontFamily: 'var(--font-mono)' }}>
          {count}
        </span>
      )}
    </button>
  );
}

function ReadRow({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return (
    <div
      className="flex items-center px-[18px] py-3.5"
      style={{ borderBottom: last ? 'none' : '1px solid rgb(var(--border))', gap: 12 }}
    >
      <div
        style={{
          minWidth: 190,
          fontFamily: 'var(--font-display)',
          fontSize: '0.8125rem',
          color: 'rgb(var(--fg-3))',
        }}
      >
        {label}
      </div>
      <div
        style={{
          flex: 1,
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          color: 'rgb(var(--fg-2))',
          textAlign: 'right',
          wordBreak: 'break-all',
        }}
      >
        {value}
      </div>
    </div>
  );
}

function EditRow({
  label,
  children,
  last = false,
}: {
  label: string;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <div
      className="flex items-center px-[18px] py-2.5"
      style={{ borderBottom: last ? 'none' : '1px solid rgb(var(--border))', gap: 12 }}
    >
      <div
        style={{
          minWidth: 190,
          fontFamily: 'var(--font-display)',
          fontSize: '0.8125rem',
          color: 'rgb(var(--fg-3))',
        }}
      >
        {label}
      </div>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

const INPUT: React.CSSProperties = {
  width: '100%',
  background: 'rgb(var(--surface-2))',
  border: '1px solid rgb(var(--border))',
  borderRadius: 'var(--r-2)',
  padding: '7px 10px',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.75rem',
  color: 'rgb(var(--fg-1))',
  outline: 'none',
};

export default function EnvironmentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [tab, setTab] = useState<Tab>('overview');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    name: '',
    platform: '',
    emulator_slug: '',
    base_image_path: '',
    working_image_path: '',
    config_path: '',
  });
  const [editSaving, setEditSaving] = useState(false);
  const [editSaveError, setEditSaveError] = useState<string | null>(null);

  const { data: environment } = useQuery<Environment>({
    queryKey: ['environment', id],
    queryFn: () => apiFetch<Environment>(`/api/v1/environment-items/${id}`),
    enabled: !!id,
  });

  // Seeds notes once per environment id, not on every background refetch of the
  // same environment (e.g. after handleSaveNotes's own invalidateQueries), so
  // the textarea isn't clobbered mid-edit. Adjusted during render (tracking
  // the previous environment id) rather than in a useEffect: a plain local
  // setState call, matching the old effect's [environment?.id] deps exactly.
  const [seededEnvironmentId, setSeededEnvironmentId] = useState<number | undefined>(undefined);
  if (environment && environment.id !== seededEnvironmentId) {
    setSeededEnvironmentId(environment.id);
    setNotes(environment.notes ?? '');
  }

  async function handleSaveNotes() {
    if (!environment) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await apiFetch(`/api/v1/environment-items/${environment.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ notes: notes.trim() || null }),
      });
      await queryClient.invalidateQueries({ queryKey: ['environments'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  function startEditing() {
    if (!environment) return;
    setEditForm({
      name: environment.name,
      platform: environment.platform,
      emulator_slug: environment.emulator_slug,
      base_image_path: environment.base_image_path ?? '',
      working_image_path: environment.working_image_path ?? '',
      config_path: environment.config_path ?? '',
    });
    setEditSaveError(null);
    setTab('overview');
    setEditing(true);
  }

  async function handleEditSave() {
    if (!environment) return;
    setEditSaving(true);
    setEditSaveError(null);
    try {
      await apiFetch(`/api/v1/environment-items/${environment.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: editForm.name.trim(),
          platform: editForm.platform,
          emulator_slug: editForm.emulator_slug.trim(),
          base_image_path: editForm.base_image_path.trim() || null,
          working_image_path: editForm.working_image_path.trim() || null,
          config_path: editForm.config_path.trim() || null,
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ['environments'] });
      await queryClient.invalidateQueries({ queryKey: ['environment', id] });
      setEditing(false);
    } catch (err) {
      setEditSaveError(err instanceof ApiError ? err.detail : 'Save failed.');
    } finally {
      setEditSaving(false);
    }
  }

  function setField(key: keyof typeof editForm, value: string) {
    setEditForm((f) => ({ ...f, [key]: value }));
  }

  async function handleLaunch() {
    if (!environment) return;
    setLaunching(true);
    try {
      await apiFetch(`/api/v1/environment-items/${environment.id}/launch`, {
        method: 'POST',
        timeoutMs: LAUNCH_TIMEOUT_MS,
      });
    } catch (err) {
      if (err instanceof ApiError) {
        showToast(err.detail, 'error');
      } else if (err instanceof TimeoutError) {
        showToast('Launch is taking longer than expected, check if it opened.', 'info');
      } else {
        showToast('Launch failed.', 'error');
      }
    } finally {
      setLaunching(false);
    }
  }

  if (!environment) {
    return (
      <div className="p-6" style={{ color: 'rgb(var(--fg-3))' }}>
        Loading…
      </div>
    );
  }

  const platformKey = environment.platform.toUpperCase();
  const platformColor = PLATFORM_COLOR[platformKey] ?? 'rgb(var(--fg-3))';
  // Live presence check, computed fresh on every read (is_present), not a
  // persisted status column, see compute_environment_presence.
  const statusColor = environment.is_present ? 'rgb(var(--success))' : 'rgb(var(--error))';
  const statusLabel = environment.is_present ? 'Present' : 'Not present';
  const BTN: React.CSSProperties = {
    border: 'none',
    fontFamily: 'var(--font-display)',
    fontSize: '0.8125rem',
    fontWeight: 600,
    padding: '9px 14px',
    borderRadius: 'var(--r-2)',
    cursor: 'pointer',
  };

  return (
    <div className="flex flex-col min-h-full">
      <TopBar showStatus>
        <button
          type="button"
          onClick={() => navigate('/environments')}
          style={{
            background: 'transparent',
            border: 0,
            color: 'rgb(var(--fg-1))',
            fontFamily: 'var(--font-display)',
            fontSize: '0.8125rem',
            fontWeight: 500,
            cursor: 'pointer',
            padding: '6px 10px',
          }}
        >
          ← Environments
        </button>
        <span style={{ flex: 1 }} />
        {!editing && (
          <button
            type="button"
            onClick={handleLaunch}
            disabled={launching}
            style={{ ...BTN, background: 'rgb(var(--peach-500))', color: 'rgb(var(--accent-ink))' }}
          >
            {launching ? 'Launching…' : 'Launch'}
          </button>
        )}
        {editing ? (
          <>
            <button
              type="button"
              onClick={() => setEditing(false)}
              style={{
                ...BTN,
                background: 'rgb(var(--surface-2))',
                border: '1px solid rgb(var(--border))',
                color: 'rgb(var(--fg-2))',
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleEditSave}
              disabled={editSaving}
              style={{
                ...BTN,
                background: 'rgb(var(--peach-500))',
                color: 'rgb(var(--accent-ink))',
              }}
            >
              {editSaving ? 'Saving…' : 'Save'}
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={startEditing}
            style={{
              ...BTN,
              background: 'rgb(var(--surface-2))',
              border: '1px solid rgb(var(--border))',
              color: 'rgb(var(--fg-2))',
            }}
          >
            Edit
          </button>
        )}
      </TopBar>

      <div className="p-6">
        <div className="flex items-center gap-3 mb-4">
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '2rem',
              letterSpacing: '-0.02em',
              margin: 0,
              color: 'rgb(var(--fg-1))',
            }}
          >
            {environment.name}
          </h1>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
              fontSize: '0.6875rem',
              letterSpacing: '0.08em',
              padding: '4px 6px',
              borderRadius: 'var(--r-1)',
              border: `1px solid ${platformColor}`,
              color: platformColor,
            }}
          >
            {platformKey}
          </span>
        </div>

        <div
          className="flex gap-0"
          style={{ borderBottom: '1px solid rgb(var(--border))', marginBottom: 22 }}
        >
          <TabBtn label="Overview" active={tab === 'overview'} onClick={() => setTab('overview')} />
          <TabBtn label="Notes" active={tab === 'notes'} onClick={() => setTab('notes')} />
        </div>

        <div className="grid gap-3.5" style={{ gridTemplateColumns: '1fr 280px' }}>
          <div>
            {tab === 'overview' && (
              <div
                className="rounded-xl overflow-hidden"
                style={{
                  background: 'rgb(var(--surface-1))',
                  border: '1px solid rgb(var(--border))',
                }}
              >
                <div
                  style={{
                    padding: '14px 18px 8px',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    fontSize: '0.75rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: 'rgb(var(--fg-3))',
                  }}
                >
                  Configuration
                </div>
                {editing ? (
                  <>
                    <EditRow label="Name">
                      <input
                        value={editForm.name}
                        onChange={(e) => setField('name', e.target.value)}
                        style={INPUT}
                      />
                    </EditRow>
                    <EditRow label="Platform">
                      <select
                        value={editForm.platform}
                        onChange={(e) => setField('platform', e.target.value)}
                        style={INPUT}
                      >
                        {Object.entries(PLATFORM_LABELS).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </EditRow>
                    <EditRow label="Emulator backend">
                      <input
                        value={editForm.emulator_slug}
                        onChange={(e) => setField('emulator_slug', e.target.value)}
                        style={INPUT}
                      />
                    </EditRow>
                    <EditRow label="Base image path">
                      <input
                        value={editForm.base_image_path}
                        onChange={(e) => setField('base_image_path', e.target.value)}
                        style={INPUT}
                        placeholder="optional"
                      />
                    </EditRow>
                    <EditRow label="Working image path">
                      <input
                        value={editForm.working_image_path}
                        onChange={(e) => setField('working_image_path', e.target.value)}
                        style={INPUT}
                        placeholder="optional"
                      />
                    </EditRow>
                    <EditRow label="Config path" last>
                      <input
                        value={editForm.config_path}
                        onChange={(e) => setField('config_path', e.target.value)}
                        style={INPUT}
                        placeholder="optional"
                      />
                    </EditRow>
                    {editSaveError && (
                      <div
                        className="px-[18px] py-3"
                        style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: '0.8125rem',
                          color: 'rgb(var(--error))',
                        }}
                      >
                        ❌ {editSaveError}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <ReadRow label="Name" value={environment.name} />
                    <ReadRow label="Platform" value={platformKey} />
                    <ReadRow label="Emulator backend" value={environment.emulator_slug} />
                    <ReadRow
                      label="Base image path"
                      value={environment.base_image_path ?? 'None'}
                    />
                    <ReadRow
                      label="Working image path"
                      value={environment.working_image_path ?? 'None'}
                    />
                    <ReadRow label="Config path" value={environment.config_path ?? 'None'} last />
                  </>
                )}
              </div>
            )}

            {tab === 'notes' && (
              <div
                className="rounded-xl p-[18px]"
                style={{
                  background: 'rgb(var(--surface-1))',
                  border: '1px solid rgb(var(--border))',
                }}
              >
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={8}
                  placeholder="Notes about this environment…"
                  style={{
                    width: '100%',
                    background: 'rgb(var(--surface-2))',
                    border: '1px solid rgb(var(--border))',
                    borderRadius: 'var(--r-2)',
                    padding: '10px 12px',
                    fontFamily: 'var(--font-display)',
                    fontSize: '0.8125rem',
                    lineHeight: 1.5,
                    color: 'rgb(var(--fg-1))',
                    outline: 'none',
                    resize: 'vertical',
                  }}
                />
                {saveError && (
                  <div
                    className="mt-2"
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: '0.8125rem',
                      color: 'rgb(var(--error))',
                    }}
                  >
                    ❌ {saveError}
                  </div>
                )}
                <div className="flex justify-end mt-3">
                  <button
                    type="button"
                    onClick={handleSaveNotes}
                    disabled={saving}
                    style={{
                      ...BTN,
                      background: 'rgb(var(--peach-500))',
                      color: 'rgb(var(--accent-ink))',
                    }}
                  >
                    {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save Notes'}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-3.5">
            <div
              className="rounded-xl p-[18px]"
              style={{
                background: 'rgb(var(--surface-1))',
                border: '1px solid rgb(var(--border))',
              }}
            >
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'rgb(var(--fg-3))',
                  marginBottom: 14,
                }}
              >
                At a glance
              </div>
              <div className="flex items-center gap-2 mb-3.5">
                <span
                  className="rounded-full inline-block shrink-0"
                  style={{ width: 7, height: 7, background: statusColor }}
                />
                <span
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontWeight: 600,
                    fontSize: '0.875rem',
                    color: 'rgb(var(--fg-1))',
                  }}
                >
                  {statusLabel}
                </span>
              </div>
              {[
                { label: 'emulator', value: environment.emulator_slug },
                {
                  label: 'installed',
                  value: environment.installed_at
                    ? new Date(environment.installed_at + 'Z').toLocaleDateString()
                    : 'Not yet',
                },
              ].map(({ label, value }) => (
                <div key={label} className="mb-3 last:mb-0">
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontWeight: 600,
                      fontSize: '0.9375rem',
                      lineHeight: 1,
                      color: 'rgb(var(--fg-1))',
                    }}
                  >
                    {value}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.6875rem',
                      color: 'rgb(var(--fg-3))',
                      marginTop: 3,
                    }}
                  >
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
