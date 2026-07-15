import { useState, type KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import { swatchHex } from './swatches'
import type { components } from '@shared/types'
type TagRead = components['schemas']['TagRead']

interface Props {
  assignedTagIds: number[]
  onAssign: (tagId: number) => void
}

export default function TagCombobox({ assignedTagIds, onAssign }: Props) {
  const [input, setInput] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const { data: allTags = [] } = useQuery<TagRead[]>({
    queryKey: ['tags'],
    queryFn: () => apiFetch<TagRead[]>('/api/v1/tags'),
  })

  const assignedSet = new Set(assignedTagIds)
  // System tags are read-only, they can be filtered by but never assigned to an
  // entity, so they are excluded from the assignable options here. The backend
  // enforces the same rule with a 403 on the assignment routes.
  const filtered = allTags.filter(
    (t) => !t.is_system && !assignedSet.has(t.id) && t.name.toLowerCase().includes(input.toLowerCase()),
  )

  function handleSelect(tag: TagRead) {
    onAssign(tag.id)
    setInput('')
    setOpen(false)
    setActiveIndex(-1)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      setOpen(false)
      setActiveIndex(-1)
      return
    }
    if (!open || filtered.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => (i + 1) % filtered.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => (i <= 0 ? filtered.length - 1 : i - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIndex >= 0 && activeIndex < filtered.length) {
        handleSelect(filtered[activeIndex])
      }
    }
  }

  return (
    <div className="relative">
      <input
        value={input}
        onChange={(e) => {
          setInput(e.target.value)
          setOpen(true)
          setActiveIndex(-1)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() =>
          setTimeout(() => {
            setOpen(false)
            setActiveIndex(-1)
          }, 150)
        }
        onKeyDown={handleKeyDown}
        placeholder="Search tags…"
        className="w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100"
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full rounded-md border border-neutral-200 bg-white py-1 shadow-lg dark:border-neutral-700 dark:bg-surface-800">
          {filtered.map((tag, i) => (
            <li key={tag.id}>
              <button
                type="button"
                onMouseDown={() => handleSelect(tag)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-neutral-700 dark:text-neutral-300 ${
                  i === activeIndex
                    ? 'bg-neutral-100 dark:bg-neutral-700'
                    : 'hover:bg-neutral-100 dark:hover:bg-neutral-700'
                }`}
              >
                <span
                  className="inline-block h-[8px] w-[8px] shrink-0 rounded-full"
                  style={{ background: swatchHex(tag.color) }}
                />
                {tag.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
