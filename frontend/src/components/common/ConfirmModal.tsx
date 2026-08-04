import { useEffect, useRef, useState } from 'react';

interface ConfirmModalProps {
  open: boolean;
  title: string;
  consequence: string;
  onConfirm: (checked?: boolean) => void;
  onCancel: () => void;
  destructive?: boolean;
  checkbox?: { label: string; defaultChecked: boolean };
}

export default function ConfirmModal({
  open,
  title,
  consequence,
  onConfirm,
  onCancel,
  destructive = false,
  checkbox,
}: ConfirmModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [checked, setChecked] = useState(checkbox?.defaultChecked ?? false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  // Re-seed the checkbox from defaultChecked every time a new confirmation
  // opens, since callers may pass a different seed value on each invocation.
  useEffect(() => {
    if (open) setChecked(checkbox?.defaultChecked ?? false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="rounded-lg border border-border-strong bg-surface-1 p-[1.5em] shadow-xl backdrop:bg-black/50"
    >
      <h2 className="mb-[0.5em] text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {title}
      </h2>
      <p className="mb-[1.25em] text-sm text-neutral-600 dark:text-neutral-400">{consequence}</p>
      {checkbox && (
        <label className="mb-[1.25em] flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            className="h-4 w-4"
          />
          {checkbox.label}
        </label>
      )}
      <div className="flex justify-end gap-[0.75em]">
        <button
          type="button"
          onClick={onCancel}
          autoFocus
          className="rounded-md border border-border-strong px-[1em] py-[0.5em] text-sm font-medium text-neutral-700 transition-colors hover:bg-surface-2 dark:text-neutral-300"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => onConfirm(checkbox ? checked : undefined)}
          className={`rounded-md px-[1em] py-[0.5em] text-sm font-medium text-white transition-opacity hover:opacity-90 ${
            destructive ? 'bg-error' : 'bg-peach'
          }`}
        >
          Confirm
        </button>
      </div>
    </dialog>
  );
}
