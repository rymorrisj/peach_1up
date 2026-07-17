import { cn } from '@/lib/utils'
import { forwardRef } from 'react'
import type { TextareaHTMLAttributes } from 'react'

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  hasError?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ hasError, className, ...props }, ref) => (
    <textarea
      ref={ref}
      rows={3}
      className={cn(
        'w-full rounded-md border bg-surface-2 px-3 py-2 text-sm text-fg-1 placeholder:text-fg-3 focus:outline-none',
        hasError
          ? 'border-error focus:border-error'
          : 'border-border focus:border-peach',
        className,
      )}
      {...props}
    />
  ),
)

Textarea.displayName = 'Textarea'
