import React, { useEffect, useReducer } from 'react'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'
import { AppContext, initialState, appReducer, applyTheme } from './_AppContext'

type User = components['schemas']['UserRead']

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState, (init) => {
    applyTheme(init.theme)
    return init
  })

  useEffect(() => {
    apiFetch<User>('/api/v1/auth/me')
      .then((user) => dispatch({ type: 'SET_ACTIVE_USER', payload: user }))
      .catch(() => dispatch({ type: 'LOGOUT' }))
  }, [])

  useEffect(() => {
    function handleSessionExpired() {
      dispatch({ type: 'LOGOUT' })
    }
    window.addEventListener('session-expired', handleSessionExpired)
    return () => window.removeEventListener('session-expired', handleSessionExpired)
  }, [])

  useEffect(() => {
    function handleApiError(e: Event) {
      const message = (e as CustomEvent<string>).detail ?? 'An unexpected error occurred.'
      dispatch({ type: 'ADD_TOAST', payload: { id: crypto.randomUUID(), message } })
    }
    window.addEventListener('api-error', handleApiError)
    return () => window.removeEventListener('api-error', handleApiError)
  }, [])

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  )
}
