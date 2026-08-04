import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  count?: ReactNode;
}

export function PageHeader({ title, description, action, count }: PageHeaderProps) {
  return (
    <div className="mb-4 flex items-baseline gap-2.5">
      <h2
        className="text-lg"
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          letterSpacing: '-0.01em',
          margin: 0,
          color: 'rgb(var(--fg-1))',
        }}
      >
        {title}
      </h2>
      {count !== undefined && (
        <span
          className="text-[0.8125rem]"
          style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'rgb(var(--fg-3))' }}
        >
          {count}
        </span>
      )}
      {description && (
        <span
          className="text-[0.8125rem]"
          style={{ fontFamily: 'var(--font-display)', color: 'rgb(var(--fg-3))', marginLeft: 4 }}
        >
          {description}
        </span>
      )}
      {action && <div className="ml-auto flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}
