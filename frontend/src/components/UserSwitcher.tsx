import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Query } from '@tanstack/react-query';
import { Lock, Check } from 'lucide-react';
import { apiFetch, ApiError } from '@/api/client';
import { useAppContext } from '@/context/useAppContext';
import { Button, Input } from '@/ui';
import { cn } from '@/lib/utils';
import type { components } from '@shared/types';
type User = components['schemas']['UserItemRead'];

// Matches every Software-domain list/detail query key
// ([domain, 'list', ...]/[domain, 'detail', ...], see EntityListPage.tsx:89
// and EntityDetailPage.tsx:39), without naming game/app/media here, so a
// user switch keeps invalidating a future domain's lists and detail pages
// without this call site needing an edit when that domain is added. A
// restriction change on any domain can change what the newly-active user is
// allowed to see, so every domain's cached pages need to be treated as stale.
function isSoftwareDomainListOrDetailQuery(query: Query): boolean {
  const kind = query.queryKey[1];
  return kind === 'list' || kind === 'detail';
}

interface SwitchResponse {
  user: User;
}

function avatarInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '?';
}

const AVATAR_COLORS = [
  'bg-peach text-white',
  'bg-blue-500 text-white',
  'bg-emerald-500 text-white',
  'bg-violet-500 text-white',
  'bg-amber-500 text-white',
  'bg-rose-500 text-white',
];

function avatarColor(id: number): string {
  return AVATAR_COLORS[id % AVATAR_COLORS.length];
}

interface PinModalProps {
  user: User;
  onSuccess: (user: User) => void;
  onClose: () => void;
}

function PinModal({ user, onSuccess, onClose }: PinModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // showModal on mount
  const refCallback = (el: HTMLDialogElement | null) => {
    if (el && !el.open) {
      el.showModal();
      (dialogRef as React.MutableRefObject<HTMLDialogElement | null>).current = el;
    }
  };

  function handleDialogClose() {
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!pin || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await apiFetch<SwitchResponse>('/api/v1/auth/switch', {
        method: 'POST',
        body: JSON.stringify({ user_item_id: user.id, pin }),
      });
      onSuccess(resp.user);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : 'Switch failed.';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <dialog
      ref={refCallback}
      onClose={handleDialogClose}
      className="w-full max-w-xs rounded-xl border border-border bg-surface-1 p-6 shadow-2xl backdrop:bg-black/60"
    >
      <div className="mb-4 flex items-center gap-3">
        <div
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-full text-lg font-bold',
            avatarColor(user.id),
          )}
        >
          {avatarInitial(user.name)}
        </div>
        <div>
          <p className="font-semibold text-neutral-900 dark:text-neutral-100">{user.name}</p>
          <p className="text-xs text-neutral-400 dark:text-neutral-500">Enter PIN to switch</p>
        </div>
      </div>

      {user.is_locked ? (
        <div className="flex items-center gap-2 rounded-md bg-surface-2 p-3 text-sm text-neutral-600 dark:text-neutral-300">
          <Lock size={14} />
          Account locked, contact owner
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="pin-input"
            type="password"
            inputMode="numeric"
            pattern="\d{4,6}"
            maxLength={6}
            autoFocus
            autoComplete="off"
            placeholder="••••"
            value={pin}
            onChange={(e) => {
              setPin(e.target.value.replace(/\D/g, ''));
              setError(null);
            }}
            hasError={!!error}
            className="text-center tracking-[0.5em] text-lg"
          />
          {error && (
            <p role="alert" className="text-xs text-red-500 dark:text-red-400">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => dialogRef.current?.close()}>
              Cancel
            </Button>
            <Button type="submit" loading={submitting} disabled={pin.length < 4}>
              Switch
            </Button>
          </div>
        </form>
      )}

      {user.is_locked && (
        <div className="mt-4 flex justify-end">
          <Button variant="ghost" onClick={() => dialogRef.current?.close()}>
            Close
          </Button>
        </div>
      )}
    </dialog>
  );
}

export default function UserSwitcher() {
  const { state, dispatch } = useAppContext();
  const queryClient = useQueryClient();

  const { data: users } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/api/v1/user-items'),
    enabled: !!state.activeUser,
  });

  const [pinTarget, setPinTarget] = useState<User | null>(null);

  const activeId = state.activeUser?.id ?? null;

  function handleCardClick(user: User) {
    // Owner always requires PIN, even if already active (re-authentication)
    if (user.is_owner) {
      setPinTarget(user);
      return;
    }
    if (user.id === activeId) return;
    if (user.is_locked || user.pin_required) {
      setPinTarget(user);
      return;
    }
    // PIN-free non-owner, switch directly
    apiFetch<SwitchResponse>('/api/v1/auth/switch', {
      method: 'POST',
      body: JSON.stringify({ user_item_id: user.id, pin: '' }),
    })
      .then(({ user: switched }) => {
        dispatch({ type: 'SET_ACTIVE_USER', payload: switched });
        queryClient.invalidateQueries({ predicate: isSoftwareDomainListOrDetailQuery });
      })
      .catch(() => {
        /* silently fall back */
      });
  }

  function handlePinSuccess(switched: User) {
    dispatch({ type: 'SET_ACTIVE_USER', payload: switched });
    queryClient.invalidateQueries({ predicate: isSoftwareDomainListOrDetailQuery });
    setPinTarget(null);
  }

  if (!users || users.length <= 1) return null;

  return (
    <section aria-label="Switch account" className="mb-6">
      <div className="flex gap-3 overflow-x-auto pb-1">
        {users.map((user) => {
          const isActive = user.id === activeId;
          // Owner card is never disabled, clicking re-authenticates
          const isDisabled = isActive && !user.is_owner;
          return (
            <button
              key={user.id}
              type="button"
              onClick={() => handleCardClick(user)}
              disabled={isDisabled}
              aria-pressed={isActive}
              className={cn(
                'group flex min-w-[5.5rem] flex-col items-center gap-1.5 rounded-xl px-3 py-3 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-peach',
                isDisabled ? 'cursor-default bg-surface-2' : 'cursor-pointer hover:bg-surface-2/60',
              )}
            >
              <div className="relative">
                <div
                  className={cn(
                    'flex h-12 w-12 items-center justify-center rounded-full text-xl font-bold shadow-sm',
                    avatarColor(user.id),
                    isActive && 'ring-2 ring-peach ring-offset-2 ring-offset-surface-0',
                  )}
                >
                  {user.is_locked ? (
                    <Lock size={18} aria-hidden="true" />
                  ) : (
                    avatarInitial(user.name)
                  )}
                </div>
                {isActive && (
                  <span className="absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-peach text-white shadow">
                    <Check size={9} strokeWidth={3} aria-hidden="true" />
                  </span>
                )}
              </div>
              <span
                className={cn(
                  'max-w-[5rem] truncate text-xs font-medium',
                  isActive
                    ? 'text-neutral-900 dark:text-neutral-100'
                    : 'text-neutral-500 dark:text-neutral-400',
                )}
              >
                {user.name}
              </span>
            </button>
          );
        })}
      </div>

      {pinTarget && (
        <PinModal
          user={pinTarget}
          onSuccess={handlePinSuccess}
          onClose={() => setPinTarget(null)}
        />
      )}
    </section>
  );
}
