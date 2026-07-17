import { cn } from '@/lib/utils'
import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  hasError?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ hasError, className, ...props }, ref) => (
    <input
      ref={ref}
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

Input.displayName = 'Input'
