import { createContext } from 'react';
import type { ToastVariant } from './Toast';

export interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant, duration?: number) => string;
  dismissToast: (id: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);
