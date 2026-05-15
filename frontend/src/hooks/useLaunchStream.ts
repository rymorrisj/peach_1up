import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAppContext, type LaunchEntry } from '@/context/AppContext'

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const STREAM_URL = `${baseURL}/api/v1/launches/stream`
const MAX_BACKOFF_MS = 30_000

export function useLaunchStream() {
  const { dispatch } = useAppContext()
  const queryClient = useQueryClient()
  const esRef = useRef<EventSource | null>(null)
  const backoffRef = useRef(1000)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let destroyed = false

    function connect() {
      if (destroyed) return

      const es = new EventSource(STREAM_URL, { withCredentials: true })
      esRef.current = es

      es.addEventListener('snapshot', (e) => {
        try {
          const entries: LaunchEntry[] = JSON.parse((e as MessageEvent).data)
          dispatch({ type: 'SET_LAUNCHES', payload: entries })
        } catch {
          // Ignore malformed events
        }
      })

      es.addEventListener('started', (e) => {
        try {
          const entry: LaunchEntry = JSON.parse((e as MessageEvent).data)
          dispatch({ type: 'UPSERT_LAUNCH', payload: entry })
        } catch {}
      })

      es.addEventListener('exited', (e) => {
        try {
          const entry: LaunchEntry = JSON.parse((e as MessageEvent).data)
          if (entry.launch_id != null) {
            dispatch({ type: 'REMOVE_LAUNCH', payload: entry.launch_id })
            queryClient.invalidateQueries({ queryKey: ['launches', entry.target_type, entry.target_id] })
          }
        } catch {}
      })

      es.addEventListener('cleaned', (e) => {
        try {
          const entry: LaunchEntry = JSON.parse((e as MessageEvent).data)
          if (entry.launch_id != null) {
            dispatch({ type: 'REMOVE_LAUNCH', payload: entry.launch_id })
            queryClient.invalidateQueries({ queryKey: ['launches', entry.target_type, entry.target_id] })
          }
        } catch {}
      })

      es.onerror = () => {
        es.close()
        esRef.current = null
        if (!destroyed) {
          reconnectTimer.current = setTimeout(() => {
            backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
            connect()
          }, backoffRef.current)
        }
      }

      es.onopen = () => {
        backoffRef.current = 1000
      }
    }

    connect()

    return () => {
      destroyed = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [dispatch, queryClient])
}
