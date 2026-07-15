import { useEffect } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ToastVariant = 'success' | 'error' | 'info'

interface ToastProps {
  message: string
  variant?: ToastVariant
  duration?: number
  onDismiss: () => void
}

const VARIANT: Record<ToastVariant, string> = {
  success: 'border-green-700/50 text-green-400',
  error: 'border-error/50 text-error',
  info: 'border-surface-600 text-neutral-200',
}

export function Toast({ message, variant = 'info', duration = 5000, onDismiss }: ToastProps) {
  useEffect(() => {
    if (duration <= 0) return
    const timer = setTimeout(onDismiss, duration)
    return () => clearTimeout(timer)
  }, [onDismiss, duration])

  return (
    <div
      role="alert"
      onClick={onDismiss}
      className={cn(
        'flex cursor-pointer items-start gap-3 rounded-lg border bg-surface-800 px-4 py-3 text-sm shadow-lg transition-opacity hover:opacity-90',
        VARIANT[variant],
      )}
    >
      <span className="flex-1">{message}</span>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={(e) => {
          e.stopPropagation()
          onDismiss()
        }}
        className="shrink-0 rounded p-0.5 text-neutral-400 hover:bg-surface-700 hover:text-neutral-100"
      >
        <X size={14} />
      </button>
    </div>
  )
}
