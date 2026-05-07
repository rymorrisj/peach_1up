import type { ReactNode } from 'react'

interface FormFieldProps {
  label: string
  htmlFor?: string
  error?: string
  hint?: string
  required?: boolean
  children: ReactNode
}

export function FormField({ label, htmlFor, error, hint, required, children }: FormFieldProps) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300"
      >
        {label}
        {required && <span aria-hidden="true" className="ml-1 text-error">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">{hint}</p>
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-error">
          {error}
        </p>
      )}
    </div>
  )
}
