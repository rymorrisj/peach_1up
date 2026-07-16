import { useState } from 'react'
import type { DragEvent, ReactNode } from 'react'
import { ChevronUp, ChevronDown, GripVertical } from 'lucide-react'
import type { GameItemData } from './CollectionCard'

interface DiscOrderListProps {
  discs: GameItemData[]
  order: number[]
  onReorder: (order: number[]) => void
  disabled?: boolean
  renderActions?: (disc: GameItemData) => ReactNode
}

// Reorderable disc list for the Library edit view. Reordering is local-only —
// callers stage `order` and persist it on the page's own Save action; this
// component never writes to the API itself. Native HTML5 drag-and-drop
// (matches the drag-event pattern already used in AddMediaModal.tsx) plus
// up/down buttons for keyboard/accessibility, mirroring the same affordance
// already used for staging discs before upload.
export function DiscOrderList({ discs, order, onReorder, disabled, renderActions }: DiscOrderListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const byId = new Map(discs.map((d) => [d.id, d]))
  const ordered = order.map((id) => byId.get(id)).filter((d): d is GameItemData => !!d)

  function move(fromIndex: number, toIndex: number) {
    if (toIndex < 0 || toIndex >= order.length || fromIndex === toIndex) return
    const next = [...order]
    const [moved] = next.splice(fromIndex, 1)
    next.splice(toIndex, 0, moved)
    onReorder(next)
  }

  function handleDragStart(index: number) {
    return (e: DragEvent<HTMLLIElement>) => {
      if (disabled) return
      setDragIndex(index)
      e.dataTransfer.effectAllowed = 'move'
    }
  }

  function handleDragOver(e: DragEvent<HTMLLIElement>) {
    if (disabled) return
    e.preventDefault()
  }

  function handleDrop(index: number) {
    return (e: DragEvent<HTMLLIElement>) => {
      if (disabled) return
      e.preventDefault()
      if (dragIndex !== null) move(dragIndex, index)
      setDragIndex(null)
    }
  }

  return (
    <ul className="space-y-1.5">
      {ordered.map((disc, idx) => {
        const filename = disc.file_path.split(/[\\/]/).pop() ?? disc.file_path
        const isLaunch = idx === 0
        return (
          <li
            key={disc.id}
            draggable={!disabled}
            onDragStart={handleDragStart(idx)}
            onDragOver={handleDragOver}
            onDrop={handleDrop(idx)}
            onDragEnd={() => setDragIndex(null)}
            className={`flex items-center gap-3 rounded-md border border-neutral-700 bg-neutral-800/40 px-3 py-2 text-sm ${
              dragIndex === idx ? 'opacity-50' : ''
            }`}
          >
            <GripVertical
              size={14}
              className={`shrink-0 text-neutral-600 ${disabled ? '' : 'cursor-grab'}`}
              aria-hidden="true"
            />
            <span className="w-5 shrink-0 font-mono text-xs text-neutral-500">{idx + 1}</span>
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-neutral-400">{filename}</span>
            {isLaunch && (
              <span className="shrink-0 rounded-[4px] border border-[#ff8a5c]/40 bg-[#ff8a5c]/10 px-1.5 py-0.5 font-mono text-[10px] text-[#ff8a5c]">
                Launch target
              </span>
            )}
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => move(idx, idx - 1)}
                disabled={idx === 0 || disabled}
                className="rounded p-0.5 text-neutral-500 hover:text-neutral-200 disabled:opacity-30"
                aria-label={`Move ${filename} up`}
              >
                <ChevronUp size={14} />
              </button>
              <button
                type="button"
                onClick={() => move(idx, idx + 1)}
                disabled={idx === ordered.length - 1 || disabled}
                className="rounded p-0.5 text-neutral-500 hover:text-neutral-200 disabled:opacity-30"
                aria-label={`Move ${filename} down`}
              >
                <ChevronDown size={14} />
              </button>
            </div>
            {renderActions?.(disc)}
          </li>
        )
      })}
    </ul>
  )
}
