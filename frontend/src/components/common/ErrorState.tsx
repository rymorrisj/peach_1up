import { Button } from '@/ui';

interface ErrorStateProps {
  heading: string;
  subtext?: string;
  onRetry: () => void;
  retryLabel?: string;
}

export default function ErrorState({
  heading,
  subtext,
  onRetry,
  retryLabel = 'Retry',
}: ErrorStateProps) {
  return (
    <section
      role="alert"
      className="flex flex-col items-center justify-center gap-[1em] py-[4em] text-center"
    >
      <h2 className="text-lg font-semibold text-error">{heading}</h2>
      {subtext && (
        <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-500">{subtext}</p>
      )}
      <Button variant="secondary" onClick={onRetry}>
        {retryLabel}
      </Button>
    </section>
  );
}
