// EventRow — a single row in the LogsView timeline. Click to expand
// the JSON detail (with a copy-to-clipboard button). The kind label
// and the timestamp are the primary signal; color is reinforcement.

import { useState } from 'react';

import { type ProjectEventRow, type ProjectEventKind } from '../api/client';
import { toast } from '../components/ui';

const KIND_LABEL: Record<ProjectEventKind, string> = {
  lifecycle: 'LIFECYCLE',
  node_started: 'NODE STARTED',
  node_stopped: 'NODE STOPPED',
  link_created: 'WIRE',
  bridge_created: 'BRIDGE',
  message_sent: 'MESSAGE',
  anomaly: 'ANOMALY',
  attack_signal: 'ATTACK',
  error: 'ERROR',
};

// Per-kind left border color (per design-system §6.7).
const KIND_BORDER: Record<ProjectEventKind, string> = {
  lifecycle: 'border-l-primary',
  node_started: 'border-l-accent',
  node_stopped: 'border-l-text-muted',
  link_created: 'border-l-accent',
  bridge_created: 'border-l-accent',
  message_sent: 'border-l-accent',
  anomaly: 'border-l-warn',
  attack_signal: 'border-l-danger',
  error: 'border-l-danger',
};

const KIND_TEXT: Record<ProjectEventKind, string> = {
  lifecycle: 'text-primary',
  node_started: 'text-accent',
  node_stopped: 'text-text-muted',
  link_created: 'text-accent',
  bridge_created: 'text-accent',
  message_sent: 'text-accent',
  anomaly: 'text-warn',
  attack_signal: 'text-danger',
  error: 'text-danger',
};

export interface EventRowProps {
  event: ProjectEventRow;
  /** Optional node-name lookup for events that reference a node. */
  nodeName?: string;
}

export function EventRow({ event, nodeName }: EventRowProps) {
  const [expanded, setExpanded] = useState(false);
  const ts = event.ts ? new Date(event.ts) : null;
  const hasDetail = event.detail && Object.keys(event.detail).length > 0;

  async function copyJson() {
    try {
      const text = JSON.stringify(event.detail, null, 2);
      await navigator.clipboard.writeText(text);
      toast.success('Copied JSON');
    } catch {
      toast.error('Copy failed');
    }
  }

  return (
    <div
      className={[
        'rounded border border-border bg-bg-surface',
        'border-l-2',
        KIND_BORDER[event.kind],
      ].join(' ')}
    >
      <button
        type="button"
        onClick={() => hasDetail && setExpanded((v) => !v)}
        className={[
          'w-full flex items-baseline gap-3 px-3 py-2 text-left',
          'transition-colors hover:bg-bg-elevated',
          hasDetail ? 'cursor-pointer' : 'cursor-default',
        ].join(' ')}
      >
        {/* Timestamp */}
        <div className="text-2xs text-text-muted font-mono flex-shrink-0 w-20">
          {ts
            ? ts.toLocaleTimeString([], { hour12: false }) +
              '.' +
              String(ts.getMilliseconds()).padStart(3, '0')
            : '—'}
        </div>

        {/* Kind label */}
        <div
          className={[
            'text-2xs font-mono uppercase tracking-wider w-24 flex-shrink-0',
            KIND_TEXT[event.kind],
          ].join(' ')}
        >
          {KIND_LABEL[event.kind] ?? event.kind}
        </div>

        {/* Summary */}
        <div className="flex-1 min-w-0 text-xs text-text-primary truncate">
          {event.summary}
          {nodeName && event.node_id && (
            <span className="text-text-muted"> · {nodeName}</span>
          )}
        </div>

        {/* Expand chevron */}
        {hasDetail && (
          <div className="text-2xs text-text-muted font-mono">
            {expanded ? '▾' : '▸'}
          </div>
        )}
      </button>

      {expanded && hasDetail && (
        <div className="px-3 pb-3 pt-1 border-t border-border">
          <div className="flex items-center justify-between mb-1">
            <div className="text-2xs text-text-muted uppercase tracking-wider">
              Detail
            </div>
            <button
              type="button"
              onClick={copyJson}
              className="text-2xs font-mono text-text-muted hover:text-text-primary"
            >
              Copy JSON
            </button>
          </div>
          <pre className="text-2xs font-mono text-text-secondary bg-bg-app rounded border border-border p-2 overflow-x-auto">
            {JSON.stringify(event.detail, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
