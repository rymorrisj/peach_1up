import React, { createContext } from 'react'
import type { components } from '@shared/types'

type User = components['schemas']['UserRead']

interface LaunchEntry {
  target_type: string
  ended_at?: string | null
}

type Theme = 'dark' | 'light'

export interface Toast {
  id: string
  message: string
}

export interface AppState {
  theme: Theme
  sidebarCollapsed: boolean
  activeProfileId: number | null
  activeUser: User | null
  activeLaunches: Map<number, LaunchEntry>
  showUnauthModal: boolean
  toasts: Toast[]
}

export type AppAction =
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_ACTIVE_PROFILE'; payload: number | null }
  | { type: 'SET_ACTIVE_USER'; payload: User | null }
  | { type: 'LOGOUT' }
  | { type: 'DISMISS_UNAUTH_MODAL' }
  | { type: 'ADD_TOAST'; payload: Toast }
  | { type: 'DISMISS_TOAST'; payload: string }

export const initialState: AppState = {
  theme: 'dark',
  sidebarCollapsed: false,
  activeProfileId: null,
  activeUser: null,
  activeLaunches: new Map(),
  showUnauthModal: false,
  toasts: [],
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
      return { ...state, activeUser: action.payload, ...(action.payload !== null && { showUnauthModal: false }) }
    case 'LOGOUT':
      return { ...state, activeUser: null, showUnauthModal: true }
    case 'DISMISS_UNAUTH_MODAL':
      return { ...state, showUnauthModal: false }
    case 'ADD_TOAST':
      return { ...state, toasts: [...state.toasts, action.payload] }
    case 'DISMISS_TOAST':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.payload) }
  }
}

export interface AppContextValue {
  state: AppState
  dispatch: React.Dispatch<AppAction>
}

export const AppContext = createContext<AppContextValue | null>(null)
