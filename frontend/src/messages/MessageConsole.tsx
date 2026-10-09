// MessageConsole — per-host message history. Two side-by-side
// consoles, each tied to a node. New messages appear in real time
// over the project WebSocket (the realtime store already handles
// incoming events; this component just renders them).
//
// Design (per design-system §6.6 wire view conventions):
//   * Each row: timestamp, direction arrow, counterparty, payload
//     preview, latency.
//   * Outgoing (→) rendered in `accent` (cyan).
//   * Incoming (←) rendered in `success` (emerald).
//   * Failure / unreachable rendered in `danger`.
//   * "no messages" empty state.
//
// Why two side-by-side?
//   Watching both ends of a single message at once is the
//   pedagogical point: the user fires a packet from host A, sees
//   it leave, watches it arrive at host B, and reads the captured
//   payload on both sides. One panel = half the lesson.

import { useEffect, useMemo, useState } from 'react';

import { EmptyState, LoadingSkeleton, StatusPill } from '../components/ui';
import { TriggerAPI } from '../trigger/api';
import type { MessageRow } from '../trigger/types';
import type { ProjectNode } from '../types';

export interface MessageConsoleProps {
  projectId: string;
  nodes: ProjectNode[];
  /** Pre-select these two nodes (e.g. when reached from a host
   *  panel — left = the host, right = "All" or another node). */
  initialLeftId?: string;
  initialRightId?: string;
  /** Optional render override for the "no nodes" empty state. */
  emptyState?: React.ReactNode;
}

const POLL_INTERVAL_MS = 5000;
const MAX_ROWS = 200;

interface NodeOption {
  id: string;
  label: string;
  kind: string;
}

export function MessageConsole({
  projectId,
  nodes,
  initialLeftId,
  initialRightId,
  emptyState,
}: MessageConsoleProps) {
  const settableNodes = useMemo<NodeOption[]>(
    () =>
      nodes
        .filter((n) => n.kind === 'host' || n.kind === 'server' || n.kind === 'attacker')
        .map((n) => {
          const ip = n.interfaces.find((i) => i.ip_address)?.ip_address;
          return {
            id: n.id,
            label: ip ? `${n.name} (${ip})` : n.name,
            kind: n.kind,
          };
        }),
    [nodes],
  );

  // The "All" pseudo-node is rendered as a special id. Filtering on
  // the backend with a real node id won't work, so when "All" is
  // selected we call the project-level endpoint with no filter.
  const ALL = '__all__';

  const [left, setLeft] = useState<string>(
    initialLeftId && settableNodes.some((n) => n.id === initialLeftId)
      ? initialLeftId
      : settableNodes[0]?.id ?? ALL,
  );
  const [right, setRight] = useState<string>(
    initialRightId && settableNodes.some((n) => n.id === initialRightId)
      ? initialRightId
      : ALL,
  );

  // Each side polls /messages every 5s. We could use WS only, but
  // polling gives us a fresh snapshot on (re)connect and a
  // consistent "history" view (WS is best-effort, can miss events
  // when the user isn't on this page).
  const [leftMessages, setLeftMessages] = useState<MessageRow[] | null>(null);
  const [rightMessages, setRightMessages] = useState<MessageRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function fetchOnce(side: 'left' | 'right') {
      const nodeId = side === 'left' ? left : right;
      const filter = nodeId === ALL ? null : nodeId;
      try {
        const res = await TriggerAPI.listMessages(projectId, filter, MAX_ROWS);
        if (!alive) return;
        const rows = res.messages || [];
        if (side === 'left') setLeftMessages(rows);
        else setRightMessages(rows);
        setError(null);
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message);
      }
    }
    void fetchOnce('left');
    void fetchOnce('right');
    const t = setInterval(() => {
      void fetchOnce('left');
      void fetchOnce('right');
    }, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId, left, right]);

  if (settableNodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        {emptyState ?? (
          <EmptyState
            title="No hosts in this project"
            description="Add a host (or server) on the canvas to see its message history here."
          />
        )}
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 gap-3 p-3">
        <ConsolePanel
          title="Left"
          nodes={settableNodes}
          allId={ALL}
          value={left}
          onChange={setLeft}
          messages={leftMessages}
          error={error}
        />
        <ConsolePanel
          title="Right"
          nodes={settableNodes}
          allId={ALL}
          value={right}
          onChange={setRight}
          messages={rightMessages}
          error={error}
        />
      </div>
    </div>
  );
}

// ─── single panel ────────────────────────────────────────────────

interface ConsolePanelProps {
  title: string;
  nodes: NodeOption[];
  allId: string;
  value: string;
  onChange: (v: string) => void;
  messages: MessageRow[] | null;
  error: string | null;
}

function ConsolePanel({
  title,
  nodes,
  allId,
  value,
  onChange,
  messages,
  error,
}: ConsolePanelProps) {
  const node = nodes.find((n) => n.id === value);
  const label = value === allId ? `All hosts` : (node?.label ?? '—');
  // When a specific host is selected we can infer direction
  // (in/out) by comparing row.src_node_id to the panel's host id.
  // "All" mode has no anchor → direction is unknown.
  const hostId = value === allId ? null : value;
  return (
    <div className="flex flex-col min-h-0 bg-bg-surface border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 flex-shrink-0">
        <span className="text-2xs font-semibold uppercase tracking-wider text-text-muted">
          {title}
        </span>
        <span className="text-sm font-semibold text-text-primary truncate flex-1">
          {label}
        </span>
        <select
          className="h-7 px-2 rounded-md bg-bg-surface-2 border border-border text-text-secondary text-xs"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={`${title} host`}
        >
          <option value={allId}>All hosts</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.label}
            </option>
          ))}
        </select>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {error && (
          <div className="m-3 rounded-md border border-danger/40 bg-danger-soft p-3 text-2xs text-danger">
            {error}
          </div>
        )}
        {!error && messages === null && (
          <div className="p-3 space-y-2">
            <LoadingSkeleton width="100%" height="32px" />
            <LoadingSkeleton width="80%" height="32px" />
            <LoadingSkeleton width="90%" height="32px" />
          </div>
        )}
        {!error && messages !== null && messages.length === 0 && (
          <EmptyState
            bare
            title="No messages yet"
            description="Send a message to this host from the canvas, or pick a different host."
          />
        )}
        {!error && messages !== null && messages.length > 0 && (
          <div className="divide-y divide-border-muted">
            {messages.map((m) => (
              <MessageRowView key={m.id} row={m} hostId={hostId} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── row ─────────────────────────────────────────────────────────

function MessageRowView({ row, hostId }: { row: MessageRow; hostId: string | null }) {
  // When filtered to a specific host, infer direction by comparing
  // row.src_node_id (and row.dst_node_id) to the panel's host id.
  // "All" mode has no anchor → direction is unknown (rendered as `·`).
  const direction: 'in' | 'out' | 'none' = !hostId
    ? 'none'
    : row.src_node_id === hostId
      ? 'out'
      : row.dst_node_id === hostId
        ? 'in'
        : 'none';
  const tone = directionForTone(row.status);
  const ts = row.created_at ? new Date(row.created_at) : null;
  const timeLabel = ts ? formatTime(ts) : '—';
  const payload = (row.payload || '').slice(0, 60) + (row.payload && row.payload.length > 60 ? '…' : '');
  const peer = row.dst_ip || '—';
  return (
    <div className="px-3 py-2 flex items-center gap-3 hover:bg-bg-surface-2">
      <span className="text-2xs font-mono text-text-muted whitespace-nowrap">
        {timeLabel}
      </span>
      <span
        className={[
          'inline-flex w-6 justify-center font-mono text-sm',
          tone.arrow,
        ].join(' ')}
        aria-label="direction"
      >
        {direction === 'in' ? '←' : direction === 'out' ? '→' : '·'}
      </span>
      <div className="flex-1 min-w-0 flex items-center gap-2">
        <span className="text-2xs font-mono text-text-secondary whitespace-nowrap">
          {row.protocol}
        </span>
        <span className="text-2xs text-text-muted truncate">→ {peer}</span>
        <span className="text-2xs font-mono text-text-primary truncate flex-1">
          {payload}
        </span>
      </div>
      <StatusPill tone={tone.pill}>{row.status}</StatusPill>
    </div>
  );
}

function directionForTone(
  status: string,
): { pill: 'running' | 'warn' | 'danger' | 'idle'; arrow: string } {
  if (status === 'delivered') return { pill: 'running', arrow: 'text-success' };
  if (status === 'unreachable') return { pill: 'warn', arrow: 'text-warn' };
  if (status === 'failed') return { pill: 'danger', arrow: 'text-danger' };
  return { pill: 'idle', arrow: 'text-text-muted' };
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
