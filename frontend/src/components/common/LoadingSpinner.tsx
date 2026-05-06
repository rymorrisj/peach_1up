interface LoadingSpinnerProps {
  label?: string
}

export default function LoadingSpinner({ label }: LoadingSpinnerProps) {
  return (
    <span role="status" className="inline-flex items-center gap-[0.5em]">
      <span
        aria-hidden="true"
        className="block h-[1em] w-[1em] animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      {label ? (
        <span className="sr-only">{label}</span>
      ) : (
        <span className="sr-only">Loading…</span>
      )}
    </span>
  )
}
