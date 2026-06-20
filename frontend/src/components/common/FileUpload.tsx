import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { getCsrfToken } from '@/api/client'

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

interface FileUploadProps {
  era: string
  mediaType: 'os' | 'game'
  onComplete: (path: string) => void
  accept?: string
}

export default function FileUpload({ era, mediaType, onComplete, accept }: FileUploadProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    upload(file)
  }

  function upload(file: File) {
    setUploading(true)
    setProgress(0)
    setError(null)

    const fd = new FormData()
    fd.append('file', file)
    fd.append('era', era)
    fd.append('media_type', mediaType)

    // XHR is required here — fetch() does not expose upload progress events.
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${baseURL}/api/v1/media/upload`)
    xhr.withCredentials = true
    xhr.setRequestHeader('X-CSRF-Token', getCsrfToken())

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        setProgress(Math.round((ev.loaded / ev.total) * 100))
      }
    }

    xhr.onload = () => {
      setUploading(false)
      setProgress(null)
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const result = JSON.parse(xhr.responseText) as { path: string }
          onComplete(result.path)
        } catch {
          setError('Upload succeeded but the response could not be parsed.')
        }
      } else {
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string }
          setError(body.detail ?? `Upload failed (HTTP ${xhr.status}).`)
        } catch {
          setError(`Upload failed (HTTP ${xhr.status}).`)
        }
      }
    }

    xhr.onerror = () => {
      setUploading(false)
      setProgress(null)
      setError('Network error during upload.')
    }

    xhr.send(fd)
  }

  return (
    <div className="mt-1.5 space-y-1.5">
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        disabled={uploading}
        className="text-xs text-[#ff8a5c] hover:underline disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploading ? 'Uploading…' : 'or upload a new file…'}
      </button>
      <input
        ref={fileRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        accept={accept}
        onChange={handleChange}
      />
      {progress !== null && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
          <div
            className="h-full rounded-full bg-[#ff8a5c] transition-all duration-100"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      {error && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </div>
  )
}
