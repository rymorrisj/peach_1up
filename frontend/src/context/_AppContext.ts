import React, { createContext } from 'react'
import type { components } from '@shared/types'

type User = components['schemas']['UserItemRead']

type Theme = 'dark' | 'light'

export interface BackgroundJob {
  id: string
  kind: 'upload' | 'scan'
  status: 'processing' | 'cancelling' | 'done' | 'error' | 'cancelled'
  progress: number
  message: string
  result?: unknown
  error?: string | null
}

export interface AppState {
  theme: Theme
  sidebarCollapsed: boolean
  activeProfileId: number | null
  activeUser: User | null
  authChecked: boolean
  showUnauthModal: boolean
  backgroundJobs: BackgroundJob[]
}

export type AppAction =
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_ACTIVE_PROFILE'; payload: number | null }
  | { type: 'SET_ACTIVE_USER'; payload: User | null }
  | { type: 'LOGOUT' }
  | { type: 'DISMISS_UNAUTH_MODAL' }
  | { type: 'UPSERT_JOB'; payload: BackgroundJob }
  | { type: 'SET_JOBS'; payload: BackgroundJob[] }
  | { type: 'DISMISS_JOB'; payload: string }

export const initialState: AppState = {
  theme: 'dark',
  sidebarCollapsed: false,
  activeProfileId: null,
  activeUser: null,
  authChecked: false,
  showUnauthModal: false,
  backgroundJobs: [],
}

export function applyTheme(theme: Theme) {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_THEME':
      applyTheme(action.payload)
      return { ...state, theme: action.payload }
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed }
    case 'SET_ACTIVE_PROFILE':
      return { ...state, activeProfileId: action.payload }
    case 'SET_ACTIVE_USER':
      return { ...state, activeUser: action.payload, authChecked: true, ...(action.payload !== null && { showUnauthModal: false }) }
    case 'LOGOUT':
      return { ...state, activeUser: null, authChecked: true, showUnauthModal: true }
    case 'DISMISS_UNAUTH_MODAL':
      return { ...state, showUnauthModal: false }
    case 'UPSERT_JOB': {
      const exists = state.backgroundJobs.some((j) => j.id === action.payload.id)
      return {
        ...state,
        backgroundJobs: exists
          ? state.backgroundJobs.map((j) => (j.id === action.payload.id ? action.payload : j))
          : [...state.backgroundJobs, action.payload],
      }
    }
    case 'SET_JOBS':
      return { ...state, backgroundJobs: action.payload }
    case 'DISMISS_JOB':
      return { ...state, backgroundJobs: state.backgroundJobs.filter((j) => j.id !== action.payload) }
  }
}

export interface AppContextValue {
  state: AppState
  dispatch: React.Dispatch<AppAction>
}

export const AppContext = createContext<AppContextValue | null>(null)
