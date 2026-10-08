// Button — five variants (primary, secondary, ghost, danger, accent),
// three sizes. The whole M4 dashboard funnels through this so destructive
// actions always look destructive, primary actions always look primary.

import { type ButtonHTMLAttributes, type ReactNode } from 'react';

export type ButtonVariant =
  | 'primary'   // main action on the page (cyan, filled)
  | 'secondary' // non-destructive secondary action (slate, outlined)
  | 'ghost'     // tertiary / inline (no border, hover only)
  | 'danger'    // destructive (rose, filled)
  | 'accent';   // decorative, only for special moments (cyan, glow)

export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** When true, shows a spinner and disables the button. */
  loading?: boolean;
  /** Inline icon (rendered before the label). */
  icon?: ReactNode;
}

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    'bg-accent text-text-inverse hover:bg-accent/90 active:bg-accent/80 ' +
    'shadow-sm hover:shadow-glow-accent',
  secondary:
    'bg-bg-surface-2 text-text-primary border border-border ' +
    'hover:border-border-strong hover:bg-bg-surface',
  ghost:
    'bg-transparent text-text-secondary hover:bg-bg-surface-2 ' +
    'hover:text-text-primary',
  danger:
    'bg-danger text-text-inverse hover:bg-danger/90 ' +
    'shadow-sm hover:shadow-glow-danger',
  accent:
    'bg-accent/15 text-accent border border-accent/40 ' +
    'hover:bg-accent/25 hover:border-accent/60',
};

const SIZE: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
  lg: 'h-11 px-5 text-base gap-2.5',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const classes = [
    'inline-flex items-center justify-center rounded-md font-medium',
    'transition-colors duration-fast',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base',
    'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none',
    VARIANT[variant],
    SIZE[size],
    className,
  ].join(' ');

  return (
    <button
      type="button"
      className={classes}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span
          className="inline-block w-3.5 h-3.5 border-2 border-current border-r-transparent rounded-full animate-spin"
          aria-hidden
        />
      ) : icon ? (
        <span className="inline-flex items-center" aria-hidden>
          {icon}
        </span>
      ) : null}
      {children && <span className="truncate">{children}</span>}
    </button>
  );
}
