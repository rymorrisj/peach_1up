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

Input.displayName = 'Input'
