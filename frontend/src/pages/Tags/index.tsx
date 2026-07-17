import { useEffect, useState } from 'react'
import { Lock } from 'lucide-react'
import TopBar from '@/components/layout/TopBar'
import { apiFetch, ApiError } from '@/api/client'
import { TAG_SWATCHES, swatchHex } from '@/components/Tags'
import { Button, Card } from '@/ui'

interface UserTag {
  id: number
  name: string
  item_count: number
  color: string
  is_system: boolean
}

function SwatchPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  return (
    <div className="flex gap-2" role="radiogroup" aria-label="Tag colour">
      {TAG_SWATCHES.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onChange(s.id)}
          aria-label={s.id}
          aria-checked={value === s.id}
          style={{ background: s.hex }}
          className={`h-6 w-6 rounded-full border-2 transition-transform duration-[120ms] hover:scale-110 ${
            value === s.id
              ? 'scale-100 border-accent'
              : 'border-transparent'
          }`}
        />
      ))}
    </div>
  )
}

// System tags carry no explicit category field from the backend (Tag only
// has id/name/item_count/color/is_system), but the seeder in
// backend/core/startup_seed.py assigns a distinct color per category (era
// tags -> coral, hardware tags -> amber, content-type tags -> sky), so color
// is the reliable signal for reconstructing the grouping client-side. Any
// system tag with a color outside that set falls into "Other" rather than
// being silently dropped, matching the existing "explain, don't hide"
// pattern used elsewhere in this codebase (e.g. PlatformField.tsx).
const CATEGORY_BY_COLOR: Record<string, { label: string; hint: string }> = {
  coral: { label: 'Era', hint: 'Inferred from your launch profile. Always shown first on cards.' },
  amber: { label: 'Hardware', hint: 'Detected from profile requirements (MT-32, SB16, Voodoo, …).' },
  sky: { label: 'Content type', hint: 'Set by platform metadata. Genre and category.' },
}
const CATEGORY_ORDER = ['coral', 'amber', 'sky', 'other']

function SystemTagGroup({ label, hint, items }: {
  label: string
  hint: string
  items: UserTag[]
}) {
  if (items.length === 0) return null
  return (
    <Card className="mb-3">
      <Card.Header>{label}</Card.Header>
      <p className="mb-3 text-xs normal-case tracking-normal text-fg-3">{hint}</p>
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
        {items.map((t) => {
          const hex = swatchHex(t.color)
          return (
            <div
              key={t.id}
              className="flex items-center gap-2.5 rounded-lg border border-border-strong bg-surface-0 px-2.5 py-2"
            >
              <span
                className="inline-flex items-center rounded-[4px] border border-border-strong bg-surface-3 px-[7px] py-1 font-mono text-[0.65625rem] font-medium leading-none"
                style={{ color: hex }}
              >
                <span
                  className="mr-1.5 inline-block h-[6px] w-[6px] rounded-full"
                  style={{ background: hex }}
                />
                <span className="text-neutral-600 dark:text-neutral-300">{t.name}</span>
              </span>
              <span className="ml-auto font-mono text-[0.6875rem] text-neutral-500">{t.item_count} item{t.item_count === 1 ? '' : 's'}</span>
              <span
                className="shrink-0"
                title="System tags are managed by Peach 1UP and cannot be deleted."
                aria-label="Read-only system tag"
              >
                <Lock size={12} className="text-fg-3" aria-hidden="true" />
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default function Tags() {
  const [tags, setTags] = useState<UserTag[]>([])
  const [newName, setNewName] = useState('')
  const [newSwatch, setNewSwatch] = useState('slate')
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  // Inline error surface, matching the useDeleteCollection convention of
  // capturing ApiError.detail for display. The api client also fires a global
  // api-error toast, this keeps the specific message (e.g. the 403 on deleting
  // a system tag) visible next to the action that caused it.
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<UserTag[]>('/api/v1/tags')
      .then((fetched) => {
        setTags(fetched.map((t) => ({
          id: t.id,
          name: t.name,
          item_count: t.item_count,
          color: t.color,
          is_system: t.is_system,
        })))
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load tags.'))
      .finally(() => setLoading(false))
  }, [])

  const userTags = tags.filter((t) => !t.is_system)
  const systemTags = tags.filter((t) => t.is_system)

  async function addTag() {
    const name = newName.trim()
    if (!name) return
    setError(null)
    try {
      const tag = await apiFetch<UserTag>('/api/v1/tags', {
        method: 'POST',
        body: JSON.stringify({ name, color: newSwatch }),
      })
      setTags((prev) => [
        ...prev,
        { id: tag.id, name: tag.name, item_count: tag.item_count, color: tag.color, is_system: tag.is_system },
      ])
      setNewName('')
      setNewSwatch('slate')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create tag.')
    }
  }

  async function removeTag(id: number) {
    setError(null)
    try {
      await apiFetch(`/api/v1/tags/${id}`, { method: 'DELETE' })
      setTags((prev) => prev.filter((t) => t.id !== id))
      setConfirmId(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete tag.')
    }
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Tags" />

      <div className="p-6">
      {error && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-red-500/40 bg-red-500/[0.06] px-4 py-3 font-sans text-sm text-red-500 dark:text-red-400"
        >
          {error}
        </div>
      )}

      {/* ── User tags ──────────────────────────────────────────────────────── */}
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Your tags</h2>
        <span className="font-mono text-sm text-neutral-500">{userTags.length} tags</span>
        <span className="ml-auto font-mono text-xs text-neutral-500 dark:text-neutral-500">
          Show up on library cards as neutral pills.
        </span>
      </div>

      <div className="mb-8 overflow-hidden rounded-xl border border-border-strong">
        {/* Inline create row */}
        <div className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-border-strong bg-neutral-50 px-4 py-3.5 dark:bg-surface-2/40">
          <input
            type="text"
            placeholder="New tag name — e.g. cozy-evening"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addTag() }}
            maxLength={32}
            className="rounded-lg border border-neutral-300 bg-white px-3 py-2 font-sans text-sm text-neutral-900 outline-none placeholder:text-neutral-400 focus:border-accent dark:border-neutral-700 dark:bg-surface-0 dark:text-neutral-100 dark:placeholder:text-neutral-600"
          />
          <SwatchPicker value={newSwatch} onChange={setNewSwatch} />
          <Button onClick={addTag} disabled={!newName.trim()}>
            Create tag
          </Button>
        </div>

        {/* Tag list */}
        {loading ? (
          <div className="px-4 py-8 text-center font-sans text-sm text-neutral-400 dark:text-neutral-500">
            Loading tags…
          </div>
        ) : userTags.length === 0 ? (
          <div className="px-4 py-8 text-center font-sans text-sm text-neutral-400 dark:text-neutral-500">
            No user tags yet. Create one above.
          </div>
        ) : (
          userTags.map((t) => {
            const hex = swatchHex(t.color)
            const confirming = confirmId === t.id
            return (
              <div
                key={t.id}
                className={`grid items-center gap-3 border-b border-border-strong px-4 py-3 last:border-b-0 ${
                  confirming
                    ? 'border-l-[3px] border-l-red-500 bg-red-500/[0.06]'
                    : 'hover:bg-surface-2/40'
                }`}
                style={{ gridTemplateColumns: '2rem 1fr 7rem 7rem 2rem' }}
              >
                <div
                  className="h-[18px] w-[18px] rounded-full"
                  style={{ background: hex, boxShadow: '0 0 0 1px rgb(var(--fg-inverse) / 0.06) inset' }}
                />
                <div>
                  <div className="font-sans text-sm font-medium text-neutral-900 dark:text-neutral-100">{t.name}</div>
                  <div className="font-mono text-[0.6875rem] text-neutral-400 dark:text-neutral-500">#{t.id}</div>
                </div>
                <div>
                  <span
                    className="inline-flex items-center rounded-[4px] border border-border-strong bg-surface-3 px-[7px] py-1 font-mono text-[0.65625rem] font-medium leading-none"
                    style={{ color: hex }}
                  >
                    <span
                      className="mr-1.5 inline-block h-[6px] w-[6px] rounded-full"
                      style={{ background: hex }}
                    />
                    <span className="text-neutral-600 dark:text-neutral-300">{t.name}</span>
                  </span>
                </div>
                <div className="text-right font-mono text-xs text-neutral-400 dark:text-neutral-500">
                  {t.item_count} item{t.item_count === 1 ? '' : 's'}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmId(confirming ? null : t.id)}
                  aria-label={`Delete tag ${t.name}`}
                  className="h-7 w-7 px-0 hover:text-red-400"
                >
                  ×
                </Button>

                {confirming && (
                  <div className="col-span-5 flex items-center gap-3 pt-2 font-sans text-sm text-neutral-500 dark:text-neutral-400">
                    <span>
                      Delete <strong className="text-neutral-900 dark:text-neutral-100">{t.name}</strong>?
                      {t.item_count > 0 && (
                        <> It will be removed from <strong className="text-neutral-900 dark:text-neutral-100">{t.item_count}</strong> item{t.item_count === 1 ? '' : 's'}.</>
                      )}
                    </span>
                    <div className="flex-1" />
                    <Button variant="ghost" size="sm" onClick={() => setConfirmId(null)}>
                      Cancel
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => removeTag(t.id)}>
                      Delete tag
                    </Button>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* ── System tags ────────────────────────────────────────────────────── */}
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">System tags</h2>
        <span className="font-mono text-sm text-neutral-500">read-only</span>
        <span className="ml-auto font-mono text-xs text-neutral-500">
          Managed by Peach 1UP — derived from metadata. Cannot be deleted.
        </span>
      </div>

      {loading ? (
        <div className="mb-3 overflow-hidden rounded-xl border border-border-strong px-4 py-8 text-center font-sans text-sm text-neutral-400 dark:text-neutral-500">
          Loading system tags…
        </div>
      ) : systemTags.length === 0 ? (
        <div className="mb-3 overflow-hidden rounded-xl border border-border-strong px-4 py-8 text-center font-sans text-sm text-neutral-400 dark:text-neutral-500">
          No system tags.
        </div>
      ) : (
        CATEGORY_ORDER.map((key) => {
          const category = CATEGORY_BY_COLOR[key]
          const items = key === 'other'
            ? systemTags.filter((t) => !(t.color in CATEGORY_BY_COLOR))
            : systemTags.filter((t) => t.color === key)
          return (
            <SystemTagGroup
              key={key}
              label={category?.label ?? 'Other'}
              hint={category?.hint ?? 'System tags that do not match a known category.'}
              items={items}
            />
          )
        })
      )}
      </div>
    </div>
  )
}
