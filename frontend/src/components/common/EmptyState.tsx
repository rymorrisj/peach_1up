import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  heading: string
  subtext?: string
  cta?: {
    label: string
    onClick: () => void
  }
}

export default function EmptyState({ icon, heading, subtext, cta }: EmptyStateProps) {
  return (
    <section className="flex flex-col items-center justify-center gap-[1em] py-[4em] text-center">
      {icon && (
        <span aria-hidden="true" className="text-neutral-300 dark:text-neutral-600">
          {icon}
        </span>
      )}
      <h2 className="text-lg font-semibold text-neutral-700 dark:text-neutral-300">{heading}</h2>
      {subtext && (
        <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-500">{subtext}</p>
      )}
      {cta && (
        <button
          type="button"
          onClick={cta.onClick}
          className="mt-[0.5em] rounded-md bg-peach px-[1em] py-[0.5em] text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          {cta.label}
        </button>
      )}
    </section>
  )
}
