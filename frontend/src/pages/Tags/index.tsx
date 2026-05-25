import { useState } from 'react'
import TopBar from '@/components/layout/TopBar'
import { ERA_LABELS } from '@/generated/constants'

interface UserTag {
  id: string
  label: string
  swatch: string
  count: number
}

const TAG_SWATCHES = [
  { id: 'slate',  hex: '#7a8499' },
  { id: 'coral',  hex: '#e07463' },
  { id: 'amber',  hex: '#d4954a' },
  { id: 'mint',   hex: '#59b87a' },
  { id: 'sky',    hex: '#5ba4cf' },
  { id: 'violet', hex: '#8b6dc4' },
  { id: 'rose',   hex: '#c46d8b' },
]

const SYSTEM_HARDWARE_TAGS = [
  { id: 'mt32',    label: 'MT-32' },
  { id: 'sb16',    label: 'Sound Blaster 16' },
  { id: 'adlib',   label: 'AdLib' },
  { id: 'voodoo1', label: 'Voodoo 1' },
  { id: 'voodoo3', label: 'Voodoo 3' },
  { id: 'gravis',  label: 'Gravis Ultrasound' },
]

const SYSTEM_CONTENT_TAGS = [
  { id: 'game',        label: 'Game' },
  { id: 'application', label: 'Application' },
  { id: 'utility',     label: 'Utility' },
  { id: 'demo',        label: 'Demo' },
  { id: 'rom-pack',    label: 'ROM Pack' },
]

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
              ? 'scale-100 border-[#ff8a5c]'
              : 'border-transparent'
          }`}
        />
      ))}
    </div>
  )
}

function SystemTagGroup({ label, hint, tagKind, items }: {
  label: string
  hint: string
  tagKind: 'era' | 'hardware' | 'content'
  items: { id: string; label: string }[]
}) {
  const pillCls =
    tagKind === 'era'
      ? 'border-[#ff8a5c]/40 bg-[#ff8a5c]/10 text-[#ff8a5c]/80 tracking-[0.08em]'
      : tagKind === 'hardware'
      ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
      : 'border-blue-500/40 bg-blue-500/10 text-blue-300'

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-neutral-800 dark:border-surface-400">
      <div className="flex items-center gap-2 border-b border-neutral-800 bg-black/40 px-4 py-3 font-mono text-xs text-neutral-400 dark:border-surface-400">
        <span className="text-neutral-300">🔒</span>
        <strong className="font-semibold text-neutral-300">{label}</strong>
        <span className="opacity-70">· {hint}</span>
      </div>
      <div className="grid gap-2 p-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
        {items.map((it) => (
          <div
            key={it.id}
            className="flex items-center gap-2.5 rounded-lg border border-neutral-800 bg-surface-950 px-2.5 py-2 dark:border-surface-400"
          >
            <span className={`inline-flex shrink-0 items-center rounded-[4px] border px-[7px] py-1 font-mono text-[10.5px] font-medium leading-none ${pillCls}`}>
              {it.label}
            </span>
            <span className="ml-auto font-mono text-[11px] text-neutral-500">{it.id}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Tags() {
  const [userTags, setUserTags] = useState<UserTag[]>([])
  const [newName, setNewName] = useState('')
  const [newSwatch, setNewSwatch] = useState('slate')
  const [confirmId, setConfirmId] = useState<string | null>(null)

  function addTag() {
    const name = newName.trim()
    if (!name) return
    const id = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    if (userTags.some((t) => t.id === id)) return
    setUserTags([...userTags, { id, label: name, swatch: newSwatch, count: 0 }])
    setNewName('')
    setNewSwatch('slate')
  }

  function removeTag(id: string) {
    setUserTags(userTags.filter((t) => t.id !== id))
    setConfirmId(null)
  }

  const swatchHex = (id: string) => TAG_SWATCHES.find((s) => s.id === id)?.hex ?? '#7a8499'

  const eraItems = Object.entries(ERA_LABELS).map(([id, label]) => ({ id, label }))

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Tags" />

      <div className="p-6">
      {/* ── User tags ──────────────────────────────────────────────────────── */}
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Your tags</h2>
        <span className="font-mono text-sm text-neutral-500">{userTags.length} tags</span>
        <span className="ml-auto font-mono text-xs text-neutral-500 dark:text-neutral-500">
          Show up on library cards as neutral pills.
        </span>
      </div>

      <div className="mb-8 overflow-hidden rounded-xl border border-neutral-200 dark:border-surface-400">
        {/* Inline create row */}
        <div className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-neutral-200 bg-neutral-50 px-4 py-3.5 dark:border-surface-400 dark:bg-surface-800/40">
          <input
            type="text"
            placeholder="New tag name — e.g. cozy-evening"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addTag() }}
            maxLength={32}
            className="rounded-lg border border-neutral-300 bg-white px-3 py-2 font-sans text-sm text-neutral-900 outline-none placeholder:text-neutral-400 focus:border-[#ff8a5c] dark:border-neutral-700 dark:bg-surface-950 dark:text-neutral-100 dark:placeholder:text-neutral-600"
          />
          <SwatchPicker value={newSwatch} onChange={setNewSwatch} />
          <button
            type="button"
            onClick={addTag}
            disabled={!newName.trim()}
            className="rounded-lg bg-[#ff8a5c] px-4 py-2 font-sans text-sm font-semibold text-[#1d0a04] transition-colors duration-[120ms] hover:bg-[#ff9469] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Create tag
          </button>
        </div>

        {/* Tag list */}
        {userTags.length === 0 ? (
          <div className="px-4 py-8 text-center font-sans text-sm text-neutral-400 dark:text-neutral-500">
            No user tags yet. Create one above.
          </div>
        ) : (
          userTags.map((t) => {
            const hex = swatchHex(t.swatch)
            const confirming = confirmId === t.id
            return (
              <div
                key={t.id}
                className={`grid items-center gap-3 border-b border-neutral-200 px-4 py-3 last:border-b-0 dark:border-surface-400 ${
                  confirming
                    ? 'border-l-[3px] border-l-red-500 bg-red-500/[0.06]'
                    : 'hover:bg-neutral-50 dark:hover:bg-surface-800/40'
                }`}
                style={{ gridTemplateColumns: '2rem 1fr 7rem 7rem 2rem' }}
              >
                <div
                  className="h-[18px] w-[18px] rounded-full"
                  style={{ background: hex, boxShadow: '0 0 0 1px rgba(255,255,255,0.06) inset' }}
                />
                <div>
                  <div className="font-sans text-sm font-medium text-neutral-900 dark:text-neutral-100">{t.label}</div>
                  <div className="font-mono text-[11px] text-neutral-400 dark:text-neutral-500">{t.id}</div>
                </div>
                <div>
                  <span
                    className="inline-flex items-center rounded-[4px] border border-neutral-300 bg-neutral-100 px-[7px] py-1 font-mono text-[10.5px] font-medium leading-none dark:border-surface-400 dark:bg-surface-400"
                    style={{ color: hex }}
                  >
                    <span
                      className="mr-1.5 inline-block h-[6px] w-[6px] rounded-full"
                      style={{ background: hex }}
                    />
                    <span className="text-neutral-600 dark:text-neutral-300">{t.label}</span>
                  </span>
                </div>
                <div className="text-right font-mono text-xs text-neutral-400 dark:text-neutral-500">
                  {t.count} item{t.count === 1 ? '' : 's'}
                </div>
                <button
                  type="button"
                  onClick={() => setConfirmId(confirming ? null : t.id)}
                  aria-label={`Delete tag ${t.label}`}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-transparent text-neutral-400 transition-colors hover:border-red-500/40 hover:text-red-400 dark:text-neutral-500"
                >
                  ×
                </button>

                {confirming && (
                  <div className="col-span-5 flex items-center gap-3 pt-2 font-sans text-sm text-neutral-500 dark:text-neutral-400">
                    <span>
                      Delete <strong className="text-neutral-900 dark:text-neutral-100">{t.label}</strong>?
                      {t.count > 0 && (
                        <> It will be removed from <strong className="text-neutral-900 dark:text-neutral-100">{t.count}</strong> item{t.count === 1 ? '' : 's'}.</>
                      )}
                    </span>
                    <div className="flex-1" />
                    <button
                      type="button"
                      onClick={() => setConfirmId(null)}
                      className="rounded-lg px-3 py-1.5 text-xs font-medium text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700 dark:text-neutral-400 dark:hover:bg-surface-400 dark:hover:text-neutral-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => removeTag(t.id)}
                      className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-medium text-red-500 transition-colors hover:bg-red-500/10 dark:text-red-400"
                    >
                      Delete tag
                    </button>
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
          Managed by Peach 1UP — derived from metadata. Cannot be edited.
        </span>
      </div>

      <SystemTagGroup
        label="Era"
        hint="Inferred from your launch profile. Always shown first on cards."
        tagKind="era"
        items={eraItems}
      />
      <SystemTagGroup
        label="Hardware"
        hint="Detected from profile requirements (MT-32, SB16, Voodoo, …)."
        tagKind="hardware"
        items={SYSTEM_HARDWARE_TAGS}
      />
      <SystemTagGroup
        label="Content type"
        hint="Set by platform metadata. Genre and category."
        tagKind="content"
        items={SYSTEM_CONTENT_TAGS}
      />
      </div>
    </div>
  )
}
