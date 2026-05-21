import { useRef, useEffect } from 'react'
import { Input, Button } from '@/ui'

interface LaunchCommandListProps {
  value: string[]
  onChange: (commands: string[]) => void
  placeholder?: string
  disabled?: boolean
}

export default function LaunchCommandList({
  value,
  onChange,
  placeholder = 'e.g. D:\\DOOMCD\\DOOM.EXE',
  disabled = false,
}: LaunchCommandListProps) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  const pendingFocusRef = useRef<number | null>(null)

  useEffect(() => {
    if (pendingFocusRef.current !== null) {
      inputRefs.current[pendingFocusRef.current]?.focus()
      pendingFocusRef.current = null
    }
  })

  function handleChange(index: number, newVal: string) {
    onChange(value.map((v, i) => (i === index ? newVal : v)))
  }

  function handleBlur(index: number) {
    if (value[index].trim() === '') {
      onChange(value.filter((_, i) => i !== index))
    }
  }

  function handleRemove(index: number) {
    onChange(value.filter((_, i) => i !== index))
  }

  function handleMoveUp(index: number) {
    if (index === 0) return
    const next = [...value]
    ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
    onChange(next)
  }

  function handleMoveDown(index: number) {
    if (index === value.length - 1) return
    const next = [...value]
    ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
    onChange(next)
  }

  function handleAdd() {
    pendingFocusRef.current = value.length
    onChange([...value, ''])
  }

  const preview = value.filter(Boolean).join(' && ') || '—'

  return (
    <div className="space-y-3">
      <div>
        <p className="mb-1 text-xs font-medium text-neutral-500 dark:text-neutral-400">
          Combined command
        </p>
        <div className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 font-mono text-xs text-neutral-700 break-all dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-300">
          {preview}
        </div>
      </div>

      <div className="space-y-2">
        {value.map((cmd, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="flex flex-col gap-0.5">
              <Button
                variant="ghost"
                size="sm"
                disabled={disabled || i === 0}
                onClick={() => handleMoveUp(i)}
                aria-label="Move up"
                className="h-5 w-5 p-0 text-[10px] leading-none"
              >
                ▲
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={disabled || i === value.length - 1}
                onClick={() => handleMoveDown(i)}
                aria-label="Move down"
                className="h-5 w-5 p-0 text-[10px] leading-none"
              >
                ▼
              </Button>
            </div>
            <Input
              ref={(el) => { inputRefs.current[i] = el }}
              value={cmd}
              placeholder={placeholder}
              disabled={disabled}
              onChange={(e) => handleChange(i, e.target.value)}
              onBlur={() => handleBlur(i)}
              className="font-mono text-xs"
            />
            <Button
              variant="ghost"
              size="sm"
              disabled={disabled}
              onClick={() => handleRemove(i)}
              aria-label="Remove command"
            >
              ✕
            </Button>
          </div>
        ))}
      </div>

      <Button variant="secondary" size="sm" disabled={disabled} onClick={handleAdd}>
        + Add command
      </Button>
    </div>
  )
}
