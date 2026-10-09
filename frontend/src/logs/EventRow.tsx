// EventRow — a single row in the LogsView timeline. Click to expand
// the JSON detail (with a copy-to-clipboard button). The kind label
// and the timestamp are the primary signal; color is reinforcement.
//
// M4 phase 08: `message_sent` events get a richer detail panel
// that explains the TCP/IP path the message took — the per-link
// hop trail with timing, plus a "View on wire" link that opens
// the first link's wire view so the user can inspect every
// frame (SYN / SYN-ACK / ACK / PSH+ACK / FIN) on that segment.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

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
  /** When provided, message_sent events can navigate to the first
   *  link's wire view via a "View on wire" button. */
  projectId?: string;
}

export function EventRow({ event, nodeName, projectId }: EventRowProps) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const ts = event.ts ? new Date(event.ts) : null;
  const hasDetail = event.detail && Object.keys(event.detail).length > 0;
  const isMessage = event.kind === 'message_sent';

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
        <div className="px-3 pb-3 pt-1 border-t border-border space-y-2">
          {/* M4 phase 08 — message_sent events get a rich TCP/IP path
              visualization. The detail may include `comm_id`,
              `dst_ip`, `protocol`, `status`, `hops_count`, and
              `payload_size`. We render a small protocol-decode
              card so the user can SEE the message, not just read
              a JSON blob. */}
          {isMessage && projectId && (
            <MessageTrail
              detail={event.detail as Record<string, unknown>}
              projectId={projectId}
              onViewWire={(linkId) =>
                navigate(`/projects/${projectId}/wires/${linkId}`)
              }
            />
          )}
          <div className="flex items-center justify-between">
            <div className="text-2xs text-text-muted uppercase tracking-wider">
              Raw detail
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

// ─── Message trail panel (M4 phase 08) ─────────────────────────────
// Renders a compact TCP/IP "what happened" card for a `message_sent`
// event. Shows the comm_id, the protocol, the destination, the
// number of hops, and a "View on wire" link that opens the first
// link's wire view (where every frame of the message is captured).

function MessageTrail({
  detail,
  projectId,
  onViewWire,
}: {
  detail: Record<string, unknown>;
  projectId: string;
  onViewWire: (linkId: string) => void;
}) {
  const commId = (detail.comm_id as string) ?? '—';
  const protocol = (detail.protocol as string) ?? '?';
  const dstIp = (detail.dst_ip as string) ?? '?';
  const status = (detail.status as string) ?? '?';
  const hopsCount = (detail.hops_count as number) ?? 0;
  const hopsCrossed = (detail.hops_crossed as string[]) ?? [];
  const payloadSize = detail.payload_size as number | null;
  const statusTone =
    status === 'delivered'
      ? 'text-success'
      : status === 'failed'
        ? 'text-danger'
        : 'text-warn';
  return (
    <div className="rounded border border-accent/30 bg-accent-soft/10 p-2 text-2xs font-mono">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="text-text-primary font-semibold">
          📨 {protocol} · {srcDstSummary(detail)}
        </div>
        <div className={['uppercase tracking-wider', statusTone].join(' ')}>
          {status}
        </div>
      </div>
      <div className="grid grid-cols-[110px_1fr] gap-1.5 text-text-secondary">
        <span className="text-text-muted">comm id</span>
        <span className="text-text-primary">{commId.slice(0, 12)}…</span>
        <span className="text-text-muted">protocol</span>
        <span className="text-text-primary">{protocol}</span>
        <span className="text-text-muted">destination</span>
        <span className="text-text-primary">{dstIp}</span>
        <span className="text-text-muted">hops</span>
        <span className="text-text-primary">
          {hopsCount} link{hopsCount === 1 ? '' : 's'}
        </span>
        {payloadSize != null && (
          <>
            <span className="text-text-muted">payload</span>
            <span className="text-text-primary">{payloadSize} B</span>
          </>
        )}
      </div>
      {hopsCrossed.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-text-muted">Path:</span>
          {hopsCrossed.map((lid, i) => (
            <span key={lid} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onViewWire(lid)}
                className="text-accent hover:underline"
                title="Open this link's wire view to see every frame of this message"
              >
                {lid.slice(0, 8)}
              </button>
              {i < hopsCrossed.length - 1 && (
                <span className="text-text-muted">→</span>
              )}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2 text-text-muted text-2xs leading-relaxed">
        Each link's wire view streams the actual frames on that segment.
        Open the first link above to see the TCP handshake
        (<span className="text-text-primary">SYN → SYN,ACK → ACK</span>),
        the data transfer (<span className="text-text-primary">PSH,ACK</span>),
        and the teardown (<span className="text-text-primary">FIN</span>).
      </div>
    </div>
  );
}

function srcDstSummary(detail: Record<string, unknown>): string {
  const src = (detail.src_node_name as string) || (detail.src_node_id as string)?.slice(0, 8) || '?';
  const dst = (detail.dst_node_name as string) || (detail.dst_node_id as string)?.slice(0, 8) || (detail.dst_ip as string) || '?';
  return `${src} → ${dst}`;
}
