import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'

type ConvertStatus = 'idle' | 'converting' | 'complete' | 'error'

interface ConvertStatusResponse {
  status: ConvertStatus
  error: string | null
  output_path: string | null
}

/** Drives POST/{id}/convert-xiso then polls its status endpoint until the
 * background conversion finishes — mirrors useLaunch's poll-for-completion
 * shape since a multi-GB rip conversion is not instant either. */
export function useXisoConvert(collectionId: number) {
  const [status, setStatus] = useState<ConvertStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current)
  }, [])

  const startMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/librarycollection/${collectionId}/convert-xiso`, { method: 'POST' }),
    onSuccess: () => {
      setStatus('converting')
      setError(null)
      pollRef.current = setInterval(async () => {
        try {
          const res = await apiFetch<ConvertStatusResponse>(
            `/api/v1/librarycollection/${collectionId}/convert-xiso/status`,
          )
          if (res.status === 'complete') {
            setStatus('complete')
            if (pollRef.current) clearInterval(pollRef.current)
          } else if (res.status === 'error') {
            setStatus('error')
            setError(res.error ?? 'Conversion failed.')
            if (pollRef.current) clearInterval(pollRef.current)
          }
        } catch {
          // transient poll errors are non-fatal
        }
      }, 3000)
    },
    onError: (err) => {
      setStatus('error')
      setError(err instanceof ApiError ? err.detail : 'Failed to start conversion.')
    },
  })

  function convert() {
    setStatus('idle')
    setError(null)
    startMutation.mutate()
  }

  return {
    convert,
    status,
    isConverting: status === 'converting' || startMutation.isPending,
    error,
  }
}
