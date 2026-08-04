import React, { createContext } from 'react';
import type { components } from '@shared/types';

type User = components['schemas']['UserItemRead'];

type Theme = 'dark' | 'light';

// Theme itself has no persistence mechanism today, initialState.theme is
// hardcoded and resets to 'dark' on every reload. Font scale is new ground,
// not a continuation of an existing pattern. Namespaced key, nothing else
// in the app currently touches localStorage at all (checked), so there is
// no collision risk.
const FONT_SCALE_STORAGE_KEY = 'peach1up:font-scale';

function readStoredFontScale(): number {
  if (typeof window === 'undefined') return 1;
  const raw = window.localStorage.getItem(FONT_SCALE_STORAGE_KEY);
  const parsed = raw ? parseFloat(raw) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

// core.jobs is an in-memory, per-process registry (see backend/core/jobs.py),
// it has no concept of "dismissed", a finished job just lingers there for an
// hour until swept. The Activity bell must survive a page reload (state.
// backgroundJobs is otherwise rebuilt from a fresh GET /api/v1/jobs on every
// mount, see AppContext's bootstrap effect), so a job the user has already
// dismissed has to be remembered client-side, or it would simply reappear on
// the next reload/poll. Same namespaced-localStorage approach as font scale
// above, no collision risk (checked, nothing else in the app touches
// localStorage).
const DISMISSED_JOBS_STORAGE_KEY = 'peach1up:dismissed-jobs';

function readStoredDismissedJobIds(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(DISMISSED_JOBS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function persistDismissedJobIds(ids: string[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(DISMISSED_JOBS_STORAGE_KEY, JSON.stringify(ids));
}

export interface BackgroundJob {
  id: string;
  kind: 'upload' | 'scan';
  status: 'processing' | 'cancelling' | 'done' | 'error' | 'cancelled';
  progress: number;
  message: string;
  result?: unknown;
  error?: string | null;
}

export interface AppState {
  theme: Theme;
  fontScale: number;
  sidebarCollapsed: boolean;
  activeProfileId: number | null;
  activeUser: User | null;
  authChecked: boolean;
  showUnauthModal: boolean;
  backgroundJobs: BackgroundJob[];
  // Snapshot of each job's status as of the last time the Activity panel was
  // opened, keyed by job id. A job counts as "unseen" (see JobsBell) whenever
  // its current status differs from this snapshot, whether that's a brand
  // new job (no entry yet) or one that has since moved to a new status the
  // user hasn't looked at, most notably reaching done/error while the panel
  // was closed. Distinct from isActiveStatus, which is about whether a job
  // is still running, not whether its current state has been viewed.
  seenJobStates: Record<string, BackgroundJob['status']>;
  // Ids the user has explicitly dismissed from the Activity list (the X
  // button in JobsBell), persisted to localStorage so a dismissal survives a
  // reload and isn't undone by the next GET /api/v1/jobs, which knows
  // nothing about "dismissed" and would otherwise keep returning the job
  // until core.jobs sweeps it an hour later.
  dismissedJobIds: string[];
}

export type AppAction =
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'SET_FONT_SCALE'; payload: number }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_ACTIVE_PROFILE'; payload: number | null }
  | { type: 'SET_ACTIVE_USER'; payload: User | null }
  | { type: 'LOGOUT' }
  | { type: 'DISMISS_UNAUTH_MODAL' }
  | { type: 'UPSERT_JOB'; payload: BackgroundJob }
  | { type: 'SET_JOBS'; payload: BackgroundJob[] }
  | { type: 'DISMISS_JOB'; payload: string }
  | { type: 'MARK_JOBS_SEEN' };

export const initialState: AppState = {
  theme: 'dark',
  fontScale: readStoredFontScale(),
  sidebarCollapsed: false,
  activeProfileId: null,
  activeUser: null,
  authChecked: false,
  showUnauthModal: false,
  backgroundJobs: [],
  seenJobStates: {},
  dismissedJobIds: readStoredDismissedJobIds(),
};

export function applyTheme(theme: Theme) {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
  if (!document.documentElement.hasAttribute('data-skin')) {
    document.documentElement.setAttribute('data-skin', 'peach-classic');
  }
}

export function applyFontScale(scale: number) {
  document.documentElement.style.setProperty('--font-scale', String(scale));
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_THEME':
      applyTheme(action.payload);
      return { ...state, theme: action.payload };
    case 'SET_FONT_SCALE':
      applyFontScale(action.payload);
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(FONT_SCALE_STORAGE_KEY, String(action.payload));
      }
      return { ...state, fontScale: action.payload };
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed };
    case 'SET_ACTIVE_PROFILE':
      return { ...state, activeProfileId: action.payload };
    case 'SET_ACTIVE_USER':
      return {
        ...state,
        activeUser: action.payload,
        authChecked: true,
        ...(action.payload !== null && { showUnauthModal: false }),
      };
    case 'LOGOUT':
      return { ...state, activeUser: null, authChecked: true, showUnauthModal: true };
    case 'DISMISS_UNAUTH_MODAL':
      return { ...state, showUnauthModal: false };
    case 'UPSERT_JOB': {
      const exists = state.backgroundJobs.some((j) => j.id === action.payload.id);
      return {
        ...state,
        backgroundJobs: exists
          ? state.backgroundJobs.map((j) => (j.id === action.payload.id ? action.payload : j))
          : [...state.backgroundJobs, action.payload],
      };
    }
    case 'SET_JOBS': {
      // Drop anything the user already dismissed, core.jobs itself has no
      // concept of dismissal and will keep returning a finished job for up
      // to an hour, without this filter a dismissed job would reappear the
      // moment this fires again (the next poll tick, or the next reload's
      // bootstrap fetch).
      const dismissed = new Set(state.dismissedJobIds);
      const backgroundJobs = action.payload.filter((j) => !dismissed.has(j.id));
      // Prune dismissed ids the backend no longer even lists (swept, so they
      // could never reappear anyway), keeps localStorage from growing
      // forever across a long-lived session.
      const incomingIds = new Set(action.payload.map((j) => j.id));
      const dismissedJobIds = state.dismissedJobIds.filter((id) => incomingIds.has(id));
      if (dismissedJobIds.length !== state.dismissedJobIds.length) {
        persistDismissedJobIds(dismissedJobIds);
      }
      return { ...state, backgroundJobs, dismissedJobIds };
    }
    case 'DISMISS_JOB': {
      const seenJobStates = Object.fromEntries(
        Object.entries(state.seenJobStates).filter(([id]) => id !== action.payload),
      );
      const dismissedJobIds = state.dismissedJobIds.includes(action.payload)
        ? state.dismissedJobIds
        : [...state.dismissedJobIds, action.payload];
      persistDismissedJobIds(dismissedJobIds);
      return {
        ...state,
        backgroundJobs: state.backgroundJobs.filter((j) => j.id !== action.payload),
        seenJobStates,
        dismissedJobIds,
      };
    }
    case 'MARK_JOBS_SEEN':
      return {
        ...state,
        seenJobStates: Object.fromEntries(state.backgroundJobs.map((j) => [j.id, j.status])),
      };
  }
}

export interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
}

export const AppContext = createContext<AppContextValue | null>(null);
