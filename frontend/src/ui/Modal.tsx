import * as Dialog from '@radix-ui/react-dialog';
import type { ReactNode } from 'react';

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  busy?: boolean;
}

export function Modal({ open, title, onClose, children, footer, busy = false }: ModalProps) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        // Radix fires this for every built in dismiss path, Escape, overlay
        // click, or an embedded Dialog.Close. Gating it here on busy is the
        // single replacement for the old cancel-event preventDefault, it
        // covers every dismiss path at the source the same way, callers that
        // also want their own footer buttons disabled while busy still do
        // that themselves, unchanged.
        if (!next && !busy) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-full max-w-[32rem] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-border-strong bg-surface-1 p-6 shadow-xl"
          onInteractOutside={(event) => {
            // ConfirmModal renders a native <dialog> as a sibling of this
            // portalled Dialog.Content, not a DOM descendant (e.g. the
            // delete-original confirmation opened from inside LibraryModal),
            // so Radix's DismissableLayer sees every click inside it as an
            // outside interaction. A click landing inside that top-layer
            // <dialog> must not dismiss this modal underneath it.
            const target = event.target instanceof Element ? event.target : null;
            if (target?.closest('dialog')) event.preventDefault();
          }}
        >
          <Dialog.Title className="mb-5 text-lg font-semibold text-fg-1">{title}</Dialog.Title>
          <div className="space-y-4">{children}</div>
          {footer && <div className="mt-6 flex justify-end gap-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
