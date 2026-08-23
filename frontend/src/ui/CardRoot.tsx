import { cn } from '@/lib/utils';
import type { HTMLAttributes, ReactNode } from 'react';

export type CardSize = 'sm' | 'md' | 'lg';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  size?: CardSize;
  children: ReactNode;
}

const SIZE: Record<CardSize, string> = {
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
};

export function CardRoot({ size = 'sm', className, children, ...props }: CardProps) {
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
  );
}
