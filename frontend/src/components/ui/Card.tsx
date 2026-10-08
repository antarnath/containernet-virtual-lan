// Card — the surface for every panel in the M4 dashboard.
// One border, one inner padding, one optional title row. The only
// visual variants are elevation (flat / raised / glow).
//
// All colors come from the design system in tailwind.config.js.
// No raw hex, no per-card overrides.

import { type ReactNode, type HTMLAttributes } from 'react';

export type CardElevation = 'flat' | 'raised' | 'glow';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  elevation?: CardElevation;
  /** Removes the default border (use for nested cards on bg-surface-2). */
  borderless?: boolean;
  /** Removes the default padding (use when the card is a canvas host). */
  flush?: boolean;
  children: ReactNode;
}

const ELEVATION: Record<CardElevation, string> = {
  flat: 'bg-bg-surface border border-border',
  raised: 'bg-bg-surface border border-border shadow-md',
  glow: 'bg-bg-surface border border-accent/40 shadow-glow-accent',
};

export function Card({
  elevation = 'flat',
  borderless = false,
  flush = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  const classes = [
    'rounded-lg',
    ELEVATION[elevation],
    borderless ? '' : '',
    flush ? '' : 'p-4',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}

// ─── Card.Title ───────────────────────────────────────────────────────────

interface CardHeaderProps {
  title: string;
  subtitle?: string;
  /** A small chip / button shown on the right (e.g. "Edit", count). */
  right?: ReactNode;
}

export function CardHeader({ title, subtitle, right }: CardHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-3 mb-3">
      <div className="min-w-0">
        <div className="text-sm font-semibold text-text-primary truncate">
          {title}
        </div>
        {subtitle && (
          <div className="text-xs text-text-muted mt-0.5 truncate">
            {subtitle}
          </div>
        )}
      </div>
      {right && <div className="flex-shrink-0">{right}</div>}
    </div>
  );
}
