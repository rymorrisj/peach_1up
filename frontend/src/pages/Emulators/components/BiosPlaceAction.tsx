import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import FileBrowser from '@/components/common/FileBrowser'
import { getCsrfToken } from '@/api/client'
import type { components } from '@shared/types'
type BiosPlaceResult = components['schemas']['BiosPlaceResult']
type BiosRequirement = components['schemas']['BiosRequirement']

// Multipart-only endpoint (accepts source_path or file uploads) — uses raw
// fetch + FormData here rather than apiFetch, matching the existing
// uploadFile.ts / FileUpload.tsx pattern: apiFetch always sets
// Content-Type: application/json, which is incompatible with a FormData body.
const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

// Slugs the backend's copy-into-place flow supports, and whether the file
// picker should let the user choose a file, a folder, or either. xbox-bios
// is deliberately absent — xemu uses its own asset-paths config flow.
const PICKER_MODE: Record<string, 'file' | 'folder' | 'both'> = {
  'ps1-bios': 'both',
  'ps2-bios': 'folder',
  '86box-roms': 'folder',
  'dreamcast-bios': 'both',
  'mesen-fds-bios': 'file',
}

export function BiosPlaceAction({ bios }: { bios: BiosRequirement }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [isPlacing, setIsPlacing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BiosPlaceResult | null>(null)

  const mode = PICKER_MODE[bios.slug]
  if (!mode) return null

  async function handleSelect(path: string) {
    setIsPlacing(true)
    setError(null)
    setResult(null)
    try {
      const fd = new FormData()
      fd.append('source_path', path)
      const res = await fetch(`${baseURL}/api/v1/bios/${bios.slug}/place`, {
        method: 'POST',
        body: fd,
        credentials: 'include',
        headers: { 'X-CSRF-Token': getCsrfToken() },
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(body.detail ?? `Placement failed (HTTP ${res.status}).`)
      }
      setResult(body as BiosPlaceResult)
      qc.invalidateQueries({ queryKey: ['bios-requirements'] })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Placement failed.')
    } finally {
      setIsPlacing(false)
    }
  }

  return (
    <div style={{ marginTop: 6 }}>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={isPlacing}
        style={{
          background: 'none', border: '1px solid var(--border)', borderRadius: 'var(--r-1)',
          padding: '4px 10px', fontFamily: 'var(--font-display)', fontSize: 12,
          color: 'var(--peach-400)', cursor: 'pointer', opacity: isPlacing ? 0.5 : 1,
        }}
      >
        {isPlacing ? 'Placing…' : 'Locate file/folder…'}
      </button>
      <FileBrowser
        open={open}
        onClose={() => setOpen(false)}
        onSelect={handleSelect}
        mode={mode}
        title={`Locate ${bios.name}`}
      />
      {error && (
        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--error)', fontFamily: 'var(--font-display)' }}>
          ❌ {error}
        </div>
      )}
      {result && result.warnings.map((w, i) => (
        <div key={i} style={{ marginTop: 6, fontSize: 12, color: '#f59e0b', fontFamily: 'var(--font-display)' }}>
          ⚠ {w}
        </div>
      ))}
      {result && result.warnings.length === 0 && result.copied.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 12, color: '#4ade80', fontFamily: 'var(--font-display)' }}>
          Placed {result.copied.length} file{result.copied.length === 1 ? '' : 's'}.
        </div>
      )}
    </div>
  )
}
