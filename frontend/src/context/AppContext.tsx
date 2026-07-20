import React, { useEffect, useReducer, useRef } from 'react'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'
import { AppContext, initialState, appReducer, applyTheme, applyFontScale } from './_AppContext'
import type { BackgroundJob } from './_AppContext'

type User = components['schemas']['UserItemRead']

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState, (init) => {
    applyTheme(init.theme)
    applyFontScale(init.fontScale)
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
          .then(({ user: refreshed }) => {
            dispatch({ type: 'SET_ACTIVE_USER', payload: refreshed })
          })
          .catch(() => {})
      })
      .catch(() => {
        dispatch({ type: 'LOGOUT' })
      })
  }, [])

  useEffect(() => {
    function handleSessionExpired() {
      dispatch({ type: 'LOGOUT' })
    }
    window.addEventListener('session-expired', handleSessionExpired)
    return () => window.removeEventListener('session-expired', handleSessionExpired)
  }, [])

  const didMountJobsBootstrap = useRef(false)
  useEffect(() => {
    // Without this, state.backgroundJobs only ever gets populated by a job
    // the current tab itself just started (UPSERT_JOB) or by the poll below,
    // which only runs once a job is already known to be active, so a job
    // that finished (or is still running) before this tab loaded would never
    // show up at all. core.jobs retains finished jobs for an hour (see
    // backend/core/jobs.py), so this makes the Activity bell reflect that
    // full backend-known list immediately on load, not just this session's
    // own activity, matching "stays in the nav until manually cleared".
    // Guarded the same way as the auth-check effect above, against
    // StrictMode's double-invoke of mount effects in dev.
    if (didMountJobsBootstrap.current) return
    didMountJobsBootstrap.current = true
    apiFetch<BackgroundJob[]>('/api/v1/jobs')
      .then((jobs) => dispatch({ type: 'SET_JOBS', payload: jobs }))
      .catch(() => {})
  }, [])

  // Poll background jobs (upload finalize, large scans) while any is processing
  // or cancelling — 'cancelling' still needs polling to observe the eventual
  // 'cancelled' transition once the job loop actually stops. Keyed on the
  // active-job count so the interval stays stable across progress ticks and
  // tears down once everything has finished.
  const activeJobCount = state.backgroundJobs.filter(
    (j) => j.status === 'processing' || j.status === 'cancelling',
  ).length
  useEffect(() => {
    if (activeJobCount === 0) return
    const iv = setInterval(() => {
      apiFetch<BackgroundJob[]>('/api/v1/jobs')
        .then((jobs) => dispatch({ type: 'SET_JOBS', payload: jobs }))
        .catch(() => {})
    }, 1500)
    return () => clearInterval(iv)
  }, [activeJobCount])

  // Emit 'upload-complete' whenever an upload job transitions processing → done
  // so the library grid can invalidate without polling or a manual refresh.
  // Also surfaces delete_original_error from the job result — the background
  // path-import counterpart to AddMediaModal's inline-response handling.
  // Uses a toast rather than component-local state because a background job
  // can finish after the modal that started it has already closed.
  const prevJobsRef = useRef<BackgroundJob[]>([])
  useEffect(() => {
    const prev = prevJobsRef.current
    const justFinished = state.backgroundJobs.filter(
      (j) => j.kind === 'upload' && j.status === 'done' &&
        prev.some((p) => p.id === j.id && p.status === 'processing'),
    )
    if (justFinished.length > 0) {
      window.dispatchEvent(new CustomEvent('upload-complete'))
      for (const job of justFinished) {
        const result = job.result as { title?: string; delete_original_error?: string } | undefined
        if (result?.delete_original_error) {
          window.dispatchEvent(
            new CustomEvent('app-toast', {
              detail: {
                message: `"${result.title ?? job.message}" was added, but the original file could not be deleted: ${result.delete_original_error}`,
                variant: 'error',
              },
            }),
          )
        }
      }
    }
    prevJobsRef.current = state.backgroundJobs
  }, [state.backgroundJobs])

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  )
}
