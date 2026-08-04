interface ProgressBarProps {
  pct: number;
  // Byte-level upload progress ticks frequently (duration-100 feels
  // responsive); background-job progress is polled far less often, so a
  // slower transition (duration-300) reads as smoother rather than jumpy.
  slow?: boolean;
  className?: string;
}

export default function ProgressBar({ pct, slow = false, className }: ProgressBarProps) {
  return (
    <div
      className={`h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700 ${className ?? ''}`}
    >
      <div
        className={`h-full rounded-full bg-accent transition-all ${slow ? 'duration-300' : 'duration-100'}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
