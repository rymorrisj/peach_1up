import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '@/api/client'
import TopBar from '@/components/layout/TopBar'
import type { components } from '@shared/types'

type LaunchProfile = components['schemas']['ProfileRead']

type DriveItem = {
  id: number
  slug: string
  name: string
  size_mb: number
  era: string
  created_at: string
}

function ReadRow({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return (
    <div className="flex items-center px-[18px] py-3.5"
      style={{ borderBottom: last ? 'none' : '1px solid var(--border)', gap: 12 }}>
      <div style={{ minWidth: 180, fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)' }}>
        {label}
      </div>
      <div style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', textAlign: 'right', wordBreak: 'break-all' }}>
        {value}
      </div>
    </div>
  )
}

export default function DriveDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: drives = [] } = useQuery<DriveItem[]>({
    queryKey: ['drives'],
    queryFn: () => apiFetch<DriveItem[]>('/api/v1/drives'),
  })

  const { data: profiles = [] } = useQuery<LaunchProfile[]>({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<LaunchProfile[]>('/api/v1/profiles'),
  })

  const drive = drives.find((d) => d.slug === slug)
  const mountedTo = profiles.filter((p) => p.drive_slug === slug)

  async function handleDelete() {
    if (!drive) return
    if (!window.confirm(`Delete drive "${drive.name}"? The disk image will be permanently removed.`)) return
    try {
      const { confirmation_token } = await apiFetch<{ confirmation_token: string }>(
        `/api/v1/drives/${drive.slug}/confirm-token`,
      )
      await apiFetch(
        `/api/v1/drives/${drive.slug}?confirmation_token=${encodeURIComponent(confirmation_token)}`,
        { method: 'DELETE' },
      )
      await queryClient.invalidateQueries({ queryKey: ['drives'] })
      navigate(-1)
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : 'Delete failed.')
    }
  }

  if (drives.length > 0 && !drive) {
    return <div className="p-6" style={{ color: 'var(--fg-3)' }}>Drive not found.</div>
  }
  if (!drive) {
    return <div className="p-6" style={{ color: 'var(--fg-3)' }}>Loading…</div>
  }

  const BTN: React.CSSProperties = { fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, padding: '9px 14px', borderRadius: 'var(--r-2)', cursor: 'pointer' }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <button type="button" onClick={() => navigate(-1)}
          style={{ background: 'transparent', border: 0, color: 'var(--fg-1)', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 500, cursor: 'pointer', padding: '6px 10px' }}>
          ← Back
        </button>
        <span style={{ flex: 1 }} />
        <button type="button"
          style={{ ...BTN, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>
          Eject
        </button>
        <button type="button" onClick={handleDelete}
          style={{ ...BTN, background: 'transparent', border: '1px solid var(--error)', color: 'var(--error)' }}>
          Delete
        </button>
      </TopBar>

      <div className="p-6">
        <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, letterSpacing: '-0.02em', margin: '0 0 22px', color: 'var(--fg-1)' }}>
          {drive.name}
        </h1>

        <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <div style={{ padding: '14px 18px 8px', fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--fg-3)' }}>
            Drive
          </div>
          <ReadRow label="Drive label" value={drive.name} />
          <ReadRow label="Drive letter" value="—" />
          <ReadRow label="Image path" value="—" />
          <ReadRow label="Image size" value={`${drive.size_mb} MB`} />
          <ReadRow label="Format" value="—" />
          <ReadRow label="Era" value={drive.era.toUpperCase()} />
          <ReadRow label="Created" value={new Date(drive.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })} />
          <ReadRow label="Mounted to" value={mountedTo.length === 0 ? '—' : mountedTo.map((p) => p.name).join(', ')} last />
        </div>
      </div>
    </div>
  )
}
