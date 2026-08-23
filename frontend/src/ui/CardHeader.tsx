import { cn } from '@/lib/utils';
import type { HTMLAttributes } from 'react';

// A real heading (h2), not a div, so a page with several cards still has a
// correct heading outline for screen readers and getByRole('heading')
// queries. Tailwind's preflight resets default heading margin/font-size, so
// swapping the tag carries no visual change, the classes below are what
// actually render.
export function CardHeader({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn('mb-3 text-xs font-semibold uppercase tracking-wider text-fg-3', className)}
      {...props}
    >
      {children}
    </h2>
  );
}
