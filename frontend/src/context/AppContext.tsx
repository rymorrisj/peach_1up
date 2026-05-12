import React, { createContext, useContext, useReducer } from 'react'
import type { User } from '@/types'

type Theme = 'dark' | 'light'

interface AppState {
  theme: Theme
  sidebarCollapsed: boolean
  activeProfileId: number | null
  activeUser: User | null
}

type AppAction =
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_ACTIVE_PROFILE'; payload: number | null }
  | { type: 'SET_ACTIVE_USER'; payload: User | null }

const initialState: AppState = {
  theme: 'dark',
  sidebarCollapsed: false,
  activeProfileId: null,
  activeUser: null,
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
