import { useRef } from 'react'
import type { ChangeEvent, InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'
import { Input, Button } from '@/ui'

interface PathInputProps {
  id?: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  hasError?: boolean
  mode: 'folder' | 'file'
  accept?: string
  className?: string
}

export default function PathInput({
  id,
  value,
  onChange,
  placeholder,
  hasError,
  mode,
  accept,
  className,
}: PathInputProps) {
  const fileRef = useRef<HTMLInputElement>(null)

  function handlePickerChange(e: ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files || files.length === 0) return
    const f = files[0]
    const picked =
      mode === 'folder' && f.webkitRelativePath
        ? f.webkitRelativePath.split('/')[0]
        : f.name
    onChange(picked)
    e.target.value = ''
  }

  const dirProps: InputHTMLAttributes<HTMLInputElement> =
    mode === 'folder'
      ? ({ webkitdirectory: '', multiple: true } as InputHTMLAttributes<HTMLInputElement>)
      : {}

  return (
    <div className={cn('flex gap-2', className)}>
      <Input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        hasError={hasError}
        className="min-w-0 flex-1"
      />
      <Button
        variant="secondary"
        size="sm"
        className="shrink-0"
        onClick={() => fileRef.current?.click()}
      >
        Browse…
      </Button>
      <input
        ref={fileRef}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        accept={accept}
        onChange={handlePickerChange}
        {...dirProps}
      />
    </div>
  )
}
