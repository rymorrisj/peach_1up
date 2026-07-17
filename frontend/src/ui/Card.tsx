// Bordered container primitive. Other components compose inside of it, it
// is not an image-forward card pattern and has no shadow by default.
//
// Usage:
//   <Card>
//     <Card.Header>Metadata Provider</Card.Header>
//     <p className="text-sm text-fg-2">content...</p>
//   </Card>
//
//   <Card size="lg" className="mt-4">...</Card>
//
// Props:
//   size?: 'sm' | 'md' | 'lg'   maps to p-4 / p-5 / p-6, default 'sm' (p-4)
//   className?: string          merged onto the root, standard div props also pass through
//   children: ReactNode

import { cn } from '@/lib/utils'
import type { HTMLAttributes, ReactNode } from 'react'

type CardSize = 'sm' | 'md' | 'lg'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  size?: CardSize
  children: ReactNode
}

const SIZE: Record<CardSize, string> = {
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
}

function CardRoot({ size = 'sm', className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-[var(--r-2)] border border-border bg-surface-1',
        SIZE[size],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

// A real heading (h2), not a div, so a page with several cards still has a
// correct heading outline for screen readers and getByRole('heading')
// queries. Tailwind's preflight resets default heading margin/font-size, so
// swapping the tag carries no visual change, the classes below are what
// actually render.
function CardHeader({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        'mb-3 text-xs font-semibold uppercase tracking-wider text-fg-3',
        className,
      )}
      {...props}
    >
      {children}
    </h2>
  )
}

export const Card = Object.assign(CardRoot, { Header: CardHeader })
