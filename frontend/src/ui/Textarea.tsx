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
        'w-full rounded-md border bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:outline-none dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600',
        hasError
          ? 'border-error focus:border-error'
          : 'border-neutral-300 focus:border-peach dark:border-neutral-700 dark:focus:border-peach',
        className,
      )}
      {...props}
    />
  ),
)

Textarea.displayName = 'Textarea'
