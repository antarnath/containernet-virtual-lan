// EmptyState — the "no data" surface. Used for empty project lists,
// empty canvas, empty capture log. Always shows an icon, a title, a
// one-line explanation, and an optional CTA.
//
// Designed to feel like a deliberate choice, not an error.

import { type ReactNode } from 'react';
import { Card } from './Card';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  /** The main action (e.g. "Create project", "Drop a host"). */
  action?: ReactNode;
  className?: string;
  /** When true, renders as a non-card with no border (for canvas centers). */
  bare?: boolean;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = '',
  bare = false,
}: EmptyStateProps) {
  const content = (
    <div className="flex flex-col items-center justify-center text-center py-10 px-4">
      {icon && (
        <div className="mb-3 text-text-muted [&_svg]:w-10 [&_svg]:h-10">
          {icon}
        </div>
      )}
      <div className="text-sm font-semibold text-text-primary mb-1">
        {title}
      </div>
      {description && (
        <div className="text-xs text-text-secondary max-w-sm mb-4">
          {description}
        </div>
      )}
      {action}
    </div>
  );

  if (bare) {
    return <div className={className}>{content}</div>;
  }

  return (
    <Card className={className} borderless>
      {content}
    </Card>
  );
}
