import React, { createContext, useContext, useReducer } from 'react'
import type { components } from '@shared/types'
type User = components['schemas']['UserRead']

type Theme = 'dark' | 'light'

export interface LaunchEntry {
  launch_id: number
  target_id: number | null
  target_type: string
  pid: number
  started_at: string
  ended_at: string | null
  exit_code: number | null
  job_isolated: boolean
}

interface AppState {
  theme: Theme
  sidebarCollapsed: boolean
  activeProfileId: number | null
  activeUser: User | null
  activeLaunches: Map<number, LaunchEntry>
}

type AppAction =
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_ACTIVE_PROFILE'; payload: number | null }
  | { type: 'SET_ACTIVE_USER'; payload: User | null }
  | { type: 'SET_LAUNCHES'; payload: LaunchEntry[] }
  | { type: 'UPSERT_LAUNCH'; payload: LaunchEntry }
  | { type: 'REMOVE_LAUNCH'; payload: number }

const initialState: AppState = {
  theme: 'dark',
  sidebarCollapsed: false,
  activeProfileId: null,
  activeUser: null,
  activeLaunches: new Map(),
}

function applyTheme(theme: Theme) {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_THEME':
      applyTheme(action.payload)
      return { ...state, theme: action.payload }
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed }
    case 'SET_ACTIVE_PROFILE':
      return { ...state, activeProfileId: action.payload }
    case 'SET_ACTIVE_USER':
      return { ...state, activeUser: action.payload }
    case 'SET_LAUNCHES': {
      const m = new Map<number, LaunchEntry>()
      for (const e of action.payload) {
        m.set(e.launch_id, e)
      }
      return { ...state, activeLaunches: m }
    }
    case 'UPSERT_LAUNCH': {
      const m = new Map(state.activeLaunches)
      m.set(action.payload.launch_id, action.payload)
      return { ...state, activeLaunches: m }
    }
    case 'REMOVE_LAUNCH': {
      const m = new Map(state.activeLaunches)
      m.delete(action.payload)
      return { ...state, activeLaunches: m }
    }
  }
}

interface AppContextValue {
  state: AppState
  dispatch: React.Dispatch<AppAction>
}

const AppContext = createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState, (init) => {
    applyTheme(init.theme)
    return init
  })

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  )
}

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useAppContext must be used within AppProvider')
  return ctx
}
