import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Input, Button } from '@/ui'
import FileBrowser from '@/components/common/FileBrowser'

interface PathInputProps {
  id?: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  hasError?: boolean
  mode: 'folder' | 'file' | 'both'
  accept?: string
  className?: string
  rootPath?: string | null
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
  rootPath,
}: PathInputProps) {
  const [browserOpen, setBrowserOpen] = useState(false)

  const extensions =
    (mode === 'file' || mode === 'both') && accept
      ? accept
          .split(',')
          .map((e) => e.trim().replace(/^\./, ''))
          .join(',')
      : undefined

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
        onClick={() => setBrowserOpen(true)}
      >
        Browse…
      </Button>
      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={(path) => { onChange(path); setBrowserOpen(false) }}
        extensions={extensions}
        mode={mode}
        title={mode === 'folder' ? 'Select Folder' : 'Select File'}
        rootPath={rootPath}
      />
    </div>
  )
}
