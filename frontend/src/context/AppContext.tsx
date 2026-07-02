import React, { useEffect, useReducer, useRef } from 'react'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'
import { AppContext, initialState, appReducer, applyTheme } from './_AppContext'
import type { BackgroundJob } from './_AppContext'

type User = components['schemas']['UserRead']

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState, (init) => {
    applyTheme(init.theme)
    return init
  })
  const didMountAuthCheck = useRef(false)

  useEffect(() => {
    // Guards against StrictMode's double-invoke of mount effects in dev,
    // which would otherwise fire /auth/me -> /auth/refresh twice for the
    // same mount.
    if (didMountAuthCheck.current) return
    didMountAuthCheck.current = true
    apiFetch<User>('/api/v1/auth/me')
      .then((user) => {
        dispatch({ type: 'SET_ACTIVE_USER', payload: user })
        // Rotate the session token on every app open so sessions extend automatically.
        // Failure is non-fatal — the existing session remains valid.
        apiFetch<{ user: User }>('/api/v1/auth/refresh', { method: 'POST' })
          .then(({ user: refreshed }) => dispatch({ type: 'SET_ACTIVE_USER', payload: refreshed }))
          .catch(() => {})
      })
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

  // Poll background jobs (upload finalize, large scans) while any is processing.
  // Keyed on the active-job count so the interval stays stable across progress
  // ticks and tears down once everything has finished.
  const activeJobCount = state.backgroundJobs.filter((j) => j.status === 'processing').length
  useEffect(() => {
    if (activeJobCount === 0) return
    const iv = setInterval(() => {
      apiFetch<BackgroundJob[]>('/api/v1/jobs')
        .then((jobs) => dispatch({ type: 'SET_JOBS', payload: jobs }))
        .catch(() => {})
    }, 1500)
    return () => clearInterval(iv)
  }, [activeJobCount])

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  )
}
