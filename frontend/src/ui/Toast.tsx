import * as RadixToast from '@radix-ui/react-toast'
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
  success: 'border-success/50 text-success',
  error: 'border-error/50 text-error',
  info: 'border-border-strong text-fg-1',
}

// Old behavior treated duration <= 0 as "never auto dismiss" by skipping the
// setTimeout entirely. Radix's duration prop cannot take Infinity, a browser
// setTimeout clamps an Infinity/NaN delay to fire immediately rather than
// never, so a very large finite value is used instead to mean the same
// thing without risking an immediate close.
const NEVER_MS = 24 * 60 * 60 * 1000

export function Toast({ message, variant = 'info', duration = 5000, onDismiss }: ToastProps) {
  return (
    <RadixToast.Root
      duration={duration <= 0 ? NEVER_MS : duration}
      onOpenChange={(open) => {
        if (!open) onDismiss()
      }}
      onClick={onDismiss}
      // Radix's own default role/live-region handling is internal and not
      // guaranteed to be role="alert" on the Root itself. Set it explicitly
      // so this stays the same queryable contract it always was, both for
      // the existing tests and any future consumer.
      role="alert"
      className={cn(
        'flex cursor-pointer items-start gap-3 rounded-lg border bg-surface-2 px-4 py-3 text-sm shadow-lg',
        VARIANT[variant],
      )}
    >
      <RadixToast.Description className="flex-1">{message}</RadixToast.Description>
      <RadixToast.Close
        aria-label="Dismiss"
        onClick={(e) => e.stopPropagation()}
        className="shrink-0 rounded p-0.5 text-fg-3 hover:bg-surface-3 hover:text-fg-1"
      >
        <X size={14} />
      </RadixToast.Close>
    </RadixToast.Root>
  )
}
