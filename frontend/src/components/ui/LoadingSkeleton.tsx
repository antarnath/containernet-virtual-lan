// LoadingSkeleton — a shimmer placeholder for content that's still
// loading. Used in the project list while the API is in-flight, and
// inside the canvas while we're hydrating the project detail.
//
// Color comes from bg-surface-2 so it sits inside any surface without
// needing a per-use override.

import { type HTMLAttributes } from 'react';

interface LoadingSkeletonProps extends HTMLAttributes<HTMLDivElement> {
  /** Render a circular variant (avatars, node icons). */
  circle?: boolean;
  /** Height — defaults to a single text line. */
  height?: string;
  /** Width — defaults to full container width. */
  width?: string;
}

export function LoadingSkeleton({
  circle = false,
  height = '12px',
  width = '100%',
  className = '',
  style,
  ...rest
}: LoadingSkeletonProps) {
  return (
    <div
      className={[
        'bg-bg-surface-2 bg-gradient-to-r from-bg-surface-2 via-border/40 to-bg-surface-2',
        'bg-[length:200%_100%] animate-shimmer',
        circle ? 'rounded-full' : 'rounded-md',
        className,
      ].join(' ')}
      style={{ height, width, ...style }}
      aria-hidden
      {...rest}
    />
  );
}
