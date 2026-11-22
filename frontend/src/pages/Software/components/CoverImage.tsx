import { useState, type ReactNode } from 'react';

interface CoverImageProps {
  src: string | null | undefined;
  alt: string;
  className?: string;
  loading?: 'lazy' | 'eager';
  // Rendered instead of the image when src is falsy or the image failed to load.
  fallback: ReactNode;
}

// Cover image with a per-image failed state. A broken or 404 URL swaps to the
// caller's placeholder instead of leaving a blank box. The failed URL is
// stored, not a boolean, so a new src is tried afresh without an effect.
export function CoverImage({ src, alt, className, loading = 'lazy', fallback }: CoverImageProps) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);

  if (!src || failedSrc === src) return <>{fallback}</>;

  return (
    <img
      src={src}
      alt={alt}
      loading={loading}
      decoding="async"
      className={className}
      onError={() => setFailedSrc(src)}
    />
  );
}
