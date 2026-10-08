// AnomalyBanner — the "something just happened" alert that slides in
// at the top of a panel when a new anomaly is broadcast on the
// project's WebSocket channel.
//
// Design system contract (§6.5):
//   * Background: danger-soft
//   * Left border: 2px danger
//   * Title colour: danger
//   * Slide-in: 200ms ease-out
//   * Dismiss button: ghost variant, top-right
//
// Used by the RouterPanel (phase 03) and the logs view (phase 07).
// The banner is one-per-anomaly — the parent owns the list and
// decides when to remove an entry (on dismiss or when the WS
// server says it's resolved).

import { Button } from './Button';
import { StatusPill } from './StatusPill';

export interface AnomalyBannerProps {
  kind: string;
  severity: 'info' | 'warn' | 'danger';
  summary: string;
  detail?: string;
  createdAt?: string;
  onDismiss?: () => void;
  onClick?: () => void;
}

const KIND_LABEL: Record<string, string> = {
  arp_mac_change: 'ARP cache changed',
  neigh_stale: 'Neighbor stale',
  route_mismatch: 'Route mismatch',
};

export function AnomalyBanner({
  kind,
  severity,
  summary,
  detail,
  createdAt,
  onDismiss,
  onClick,
}: AnomalyBannerProps) {
  return (
    <div
      role={onClick ? 'button' : undefined}
      onClick={onClick}
      className={[
        'rounded-md bg-danger-soft border-l-2 border-l-danger px-3 py-2',
        'flex items-start gap-3',
        onClick ? 'cursor-pointer hover:bg-danger-soft/80' : '',
      ].join(' ')}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <div className="text-xs font-semibold text-danger">
            {KIND_LABEL[kind] || kind}
          </div>
          <StatusPill tone={severity}>{severity}</StatusPill>
          {createdAt && (
            <span className="text-2xs text-text-muted">
              {formatRelativeTime(createdAt)}
            </span>
          )}
        </div>
        <div className="text-xs text-text-primary mt-0.5">{summary}</div>
        {detail && (
          <div className="text-2xs text-text-muted font-mono mt-1 truncate">
            {detail}
          </div>
        )}
      </div>
      {onDismiss && (
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          Dismiss
        </Button>
      )}
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    const diff = Date.now() - t;
    if (diff < 5000) return 'just now';
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    return new Date(iso).toLocaleTimeString();
  } catch {
    return '';
  }
}
