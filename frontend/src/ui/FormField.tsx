import type { ReactNode } from 'react';

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}

export function FormField({ label, htmlFor, error, hint, required, children }: FormFieldProps) {
  return (
    <div>
      <div className="mb-1 flex items-center">
        <label htmlFor={htmlFor} className="block text-sm font-medium text-fg-2">
          {label}
        </label>
        {required && (
          <span aria-hidden="true" className="ml-1 text-error">
            *
          </span>
        )}
      </div>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-fg-3">{hint}</p>}
      {error && (
        <p role="alert" className="mt-1 text-xs text-error">
          {error}
        </p>
      )}
    </div>
  );
}
