import { useState, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

export interface ScanPreviewItem {
  title: string
  media_path: string
  detected_era: string | null
  is_loose: boolean
  is_zip: boolean
}

export interface ScanStatus {
  running: boolean
  preview: ScanPreviewItem[]
  error: string | null
}

export interface ImportResult {
  imported: number
  skipped: number
  errors: Array<{ path: string; reason: string }>
}

interface UseLibraryScanOptions {
  open: boolean
  onImported: () => void
}

export function useLibraryScan({ open, onImported }: UseLibraryScanOptions) {
  const [scanning, setScanning] = useState(false)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  useEffect(() => {
    if (!open) {
      setScanning(false)
      setStatus(null)
      setError(null)
      setImporting(false)
      setImportResult(null)
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
    setImportResult(null)
    setScanning(true)
    scanMutation.mutate()
  }

  async function handleImport(selectedPaths: string[]) {
    setImporting(true)
    setError(null)
    try {
      const result = await apiFetch<ImportResult>('/api/v1/library/scan/import', {
        method: 'POST',
        body: JSON.stringify({ selected: selectedPaths }),
      })
      setImportResult(result)
      if (result.imported > 0) onImported()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Import failed.')
    } finally {
      setImporting(false)
    }
  }

  return { scanning, status, error, handleScan, importing, importResult, handleImport }
}
