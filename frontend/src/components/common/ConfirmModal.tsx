import { useEffect, useRef } from 'react'

interface ConfirmModalProps {
  open: boolean
  title: string
  consequence: string
  onConfirm: () => void
  onCancel: () => void
  destructive?: boolean
}

export default function ConfirmModal({
  open,
  title,
  consequence,
  onConfirm,
  onCancel,
  destructive = false,
}: ConfirmModalProps) {
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

  return (
    <dialog
      ref={dialogRef}
      className="rounded-lg border border-neutral-200 bg-white p-[1.5em] shadow-xl backdrop:bg-black/50 dark:border-surface-400 dark:bg-surface-900"
    >
      <h2 className="mb-[0.5em] text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {title}
      </h2>
      <p className="mb-[1.25em] text-sm text-neutral-600 dark:text-neutral-400">{consequence}</p>
      <div className="flex justify-end gap-[0.75em]">
        <button
          type="button"
          onClick={onCancel}
          autoFocus
          className="rounded-md border border-neutral-200 px-[1em] py-[0.5em] text-sm font-medium text-neutral-700 transition-colors hover:bg-neutral-100 dark:border-surface-400 dark:text-neutral-300 dark:hover:bg-surface-800"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className={`rounded-md px-[1em] py-[0.5em] text-sm font-medium text-white transition-opacity hover:opacity-90 ${
            destructive ? 'bg-error' : 'bg-peach'
          }`}
        >
          Confirm
        </button>
      </div>
    </dialog>
  )
}
