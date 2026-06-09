import { useEffect } from "react";
import { X } from "lucide-react";

interface ToastItemProps {
  id: string;
  message: string;
  onDismiss: (id: string) => void;
}

export default function ToastItem({ id, message, onDismiss }: ToastItemProps) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(id), 5000);
    return () => clearTimeout(timer);
  }, [id, onDismiss]);

  return (
    <div
      role="alert"
      onClick={() => onDismiss(id)}
      className="flex cursor-pointer items-start gap-3 rounded-lg border border-surface-600 bg-surface-800 px-4 py-3 text-sm text-neutral-200 shadow-lg transition-opacity hover:opacity-90"
    >
      <span className="flex-1">{message}</span>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(id);
        }}
        className="shrink-0 rounded p-0.5 text-neutral-400 hover:bg-surface-700 hover:text-neutral-100"
      >
        <X size={14} />
      </button>
    </div>
  );
}
