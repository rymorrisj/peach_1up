import { useEffect } from 'react';
import { useToast } from '@/ui/ToastProvider';
import type { ToastVariant } from '@/ui/Toast';

// Bridges window-level toast events (fired by non-React code such as the api
// client on api-error, or AppContext's background-job watcher) into the
// ToastProvider queue. Kept out of AppContext/api client so neither has to
// depend on the ToastProvider hook directly.
export function ToastEventBridge() {
  const { showToast } = useToast();

  useEffect(() => {
    function handleApiError(e: Event) {
      const message = (e as CustomEvent<string>).detail ?? 'An unexpected error occurred.';
      showToast(message, 'error');
    }
    function handleAppToast(e: Event) {
      const { message, variant } = (e as CustomEvent<{ message: string; variant?: ToastVariant }>)
        .detail;
      showToast(message, variant ?? 'info');
    }
    window.addEventListener('api-error', handleApiError);
    window.addEventListener('app-toast', handleAppToast);
    return () => {
      window.removeEventListener('api-error', handleApiError);
      window.removeEventListener('app-toast', handleAppToast);
    };
  }, [showToast]);

  return null;
}
