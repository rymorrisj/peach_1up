import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

interface ScanResult {
  folder_path: string
  name: string
  executable_path: string | null
}

export interface ScanStatus {
  running: boolean
  progress: number
  total: number
  results: ScanResult[]
}

interface UseLibraryScanOptions {
  open: boolean
  onImported: () => void
}

export function useLibraryScan({ open, onImported }: UseLibraryScanOptions) {
  const [scanning, setScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  useEffect(() => {
    if (!open) {
      setScanning(false)
      setStatus(null)
      setError(null)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [open])

  const scanMutation = useMutation<void, Error>({
    mutationFn: () => apiFetch('/api/v1/library/scan', { method: 'POST' }),
    onSuccess: () => {
      setScanning(true)
      pollRef.current = setInterval(async () => {
        try {
          const s = await apiFetch<ScanStatus>('/api/v1/library/scan/status')
          setStatus(s)
          if (!s.running) {
            clearInterval(pollRef.current!)
            setScanning(false)
            if (s.results.length > 0) onImported()
          }
        } catch {
          clearInterval(pollRef.current!)
          setScanning(false)
        }
      }, 1000)
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Scan failed.')
      setScanning(false)
    },
  })

  function handleScan() {
    setError(null)
    setStatus(null)
    setScanning(true)
    scanMutation.mutate()
  }

  return { scanning, status, error, handleScan }
}
