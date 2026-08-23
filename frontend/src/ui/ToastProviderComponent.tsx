import { useCallback, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import * as RadixToast from '@radix-ui/react-toast';
import { Toast } from './Toast';
import type { ToastVariant } from './Toast';
import { ToastContext } from './ToastContext';

interface ToastEntry {
  id: string;
  message: string;
  variant: ToastVariant;
  duration?: number;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = 'info', duration?: number) => {
      const id = crypto.randomUUID();
      setToasts((current) => [...current, { id, message, variant, duration }]);
      return id;
    },
    [],
  );

  return (
    <ToastContext.Provider value={{ showToast, dismissToast }}>
      <RadixToast.Provider swipeDirection="right">
        {children}
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            message={toast.message}
            variant={toast.variant}
            duration={toast.duration}
            onDismiss={() => dismissToast(toast.id)}
          />
        ))}
        {/* Each Toast.Root above portals itself into this Viewport via Radix's
            own internal context, wherever it is authored in the tree. The
            Viewport itself is portaled to document.body here (same as the
            old createPortal usage) so its fixed positioning is never at the
            mercy of a stacking context created by some ancestor between here
            and the app root, ToastProvider wraps the entire app in main.tsx. */}
        {createPortal(
          <RadixToast.Viewport className="fixed bottom-4 right-4 z-[9999] flex w-80 flex-col gap-2 outline-none" />,
          document.body,
        )}
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}
