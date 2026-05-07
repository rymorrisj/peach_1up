import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

interface ModalProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}

export function Modal({ open, title, onClose, children, footer }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const handleClose = () => onClose()
    dialog.addEventListener('close', handleClose)
    return () => dialog.removeEventListener('close', handleClose)
  }, [onClose])

  return (
    <dialog
      ref={dialogRef}
      className="w-full max-w-[32rem] rounded-lg border border-neutral-200 bg-white p-6 shadow-xl backdrop:bg-black/50 dark:border-surface-400 dark:bg-surface-900"
    >
      <h2 className="mb-5 text-lg font-semibold text-neutral-900 dark:text-neutral-100">{title}</h2>
      <div className="space-y-4">{children}</div>
      {footer && <div className="mt-6 flex justify-end gap-3">{footer}</div>}
    </dialog>
  )
}
