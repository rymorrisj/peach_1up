import { useEffect, useRef } from 'react'

interface ErrorOption {
  label: string
  handler: () => void
}

interface ErrorModalProps {
  open: boolean
  title: string
  cause: string
  options: ErrorOption[]
}

export default function ErrorModal({ open, title, cause, options }: ErrorModalProps) {
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
        ❌ {title}
      </h2>
      <p className="mb-[1.25em] text-sm text-neutral-600 dark:text-neutral-400">{cause}</p>
      <div className="flex flex-wrap gap-[0.75em]">
        {options.map((opt, i) => (
          <button
            key={opt.label}
            type="button"
            onClick={opt.handler}
            autoFocus={i === 0}
            className="rounded-md bg-peach px-[1em] py-[0.5em] text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            {opt.label}
          </button>
        ))}
      </div>
    </dialog>
  )
}
