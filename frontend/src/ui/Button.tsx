import { cn } from '@/lib/utils'
import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'destructive' | 'ghost'
type Size = 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

const VARIANT: Record<Variant, string> = {
  primary: 'bg-peach text-white hover:opacity-90',
  secondary:
    'bg-neutral-100 text-neutral-700 hover:bg-neutral-200 dark:bg-surface-700 dark:text-neutral-300 dark:hover:bg-surface-600',
  destructive: 'bg-error text-white hover:opacity-90',
  ghost: 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-surface-800 dark:hover:text-neutral-100',
}

const SIZE: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-[1em] py-[0.5em] text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  children,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}
