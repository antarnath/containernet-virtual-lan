// TriggerPanel — the modal for sending a message from one host to
// another host or to an arbitrary IP.
//
// Reached via:
//   * the "+ Send" button in the project header
//   * the "Send" button in a host's side panel (pre-filled source)
//
// Form fields:
//   From      — dropdown of host/server nodes in this project
//   To        — dropdown of host/server nodes + free-text IP
//   Protocol  — HTTP / TCP / ICMP radio
//   Payload   — free text
//   Preview   — live-resolved route, refreshed on every field change
//
// On Submit: POST /communications. On success, close the modal and
// the wire view (if open) starts highlighting the hops in the
// resolved route via the realtime store's packet events.
//
// The route resolver runs on every change of {src, dst} with a
// debounce (200ms) — cheap, since resolve_route is a pure function
// of the project topology and we have the topology in memory.

import { useEffect, useMemo, useRef, useState } from 'react';

import { Button, StatusPill, toast } from '../components/ui';
import { TriggerAPI } from './api';
import type { Hop, RouteResponse } from './types';
import type { ProjectNode } from '../types';

export type Protocol = 'HTTP' | 'TCP' | 'ICMP';

interface TriggerPanelProps {
  projectId: string;
  nodes: ProjectNode[];
  /** Pre-fill the source (e.g. from a host panel). */
  initialSrcNodeId?: string;
  /** Close handler. */
  onClose: () => void;
  /** Called after a successful send. The parent may use it to
   *  open the wire view or scroll to the latest message. */
  onSent?: (result: { messageId: string; hopsCrossed: string[] }) => void;
}

// Helper: list of nodes that can be the source/destination of a
// message. Hosts, servers, attackers — anything that runs an
// agent that exposes /send. Routers and switches don't run an
// agent, so we exclude them from the dropdowns.
function isSettableKind(kind: string): boolean {
  return kind === 'host' || kind === 'server' || kind === 'attacker';
}

const PROTOCOLS: Protocol[] = ['HTTP', 'TCP', 'ICMP'];

const PROTOCOL_HINT: Record<Protocol, string> = {
  HTTP: 'sent as the request body',
  TCP: 'sent as raw TCP data on port 9000',
  ICMP: 'payload is ignored — only the ping matters',
};

export function TriggerPanel({
  projectId,
  nodes,
  initialSrcNodeId,
  onClose,
  onSent,
}: TriggerPanelProps) {
  // ─── form state ─────────────────────────────────────────────
  const settable = useMemo(
    () => nodes.filter((n) => isSettableKind(n.kind)),
    [nodes],
  );

  const defaultSrc = initialSrcNodeId ?? settable[0]?.id ?? '';
  const [srcNodeId, setSrcNodeId] = useState(defaultSrc);
  const [dstKind, setDstKind] = useState<'node' | 'ip'>('node');
  const [dstNodeId, setDstNodeId] = useState(settable.find((n) => n.id !== defaultSrc)?.id ?? '');
  const [dstIp, setDstIp] = useState('');
  const [protocol, setProtocol] = useState<Protocol>('HTTP');
  const [payload, setPayload] = useState('hello');

  // ─── route preview state ────────────────────────────────────
  const [route, setRoute] = useState<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'ok'; data: RouteResponse }
    | { kind: 'unreachable'; message: string }
    | { kind: 'loop'; visited: string[] }
    | { kind: 'error'; message: string }
  >({ kind: 'idle' });

  // ─── send state ─────────────────────────────────────────────
  const [sending, setSending] = useState(false);

  // ─── resolve the destination string for the resolver ───────
  const effectiveDst = useMemo(() => {
    if (dstKind === 'ip') return dstIp.trim();
    const node = settable.find((n) => n.id === dstNodeId);
    if (!node) return '';
    // Use the first interface IP — the resolver will then match
    // it via the link's subnet_cidr.
    const iface = node.interfaces.find((i) => i.ip_address);
    return iface?.ip_address ?? '';
  }, [dstKind, dstNodeId, dstIp, settable]);

  // ─── debounced route resolution ────────────────────────────
  const debounceRef = useRef<number | null>(null);
  useEffect(() => {
    if (!srcNodeId || !effectiveDst) {
      setRoute({ kind: 'idle' });
      return;
    }
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }
    setRoute({ kind: 'loading' });
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await TriggerAPI.resolveRoute(projectId, srcNodeId, effectiveDst);
        if (res.error === 'routing_loop') {
          setRoute({
            kind: 'loop',
            visited: res.visited || [],
          });
        } else if (res.error === 'unreachable') {
          setRoute({
            kind: 'unreachable',
            message: res.detail?.error || 'No route to destination',
          });
        } else if (res.error) {
          setRoute({ kind: 'error', message: res.error });
        } else {
          setRoute({ kind: 'ok', data: res });
        }
      } catch (e) {
        setRoute({ kind: 'error', message: (e as Error).message });
      }
    }, 200);
    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [projectId, srcNodeId, effectiveDst]);

  // ─── close on Escape ────────────────────────────────────────
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // ─── submit ─────────────────────────────────────────────────
  const canSend =
    !!srcNodeId &&
    !!effectiveDst &&
    route.kind === 'ok' &&
    !sending;

  async function handleSend() {
    if (!canSend) return;
    setSending(true);
    try {
      const result = await TriggerAPI.send(projectId, {
        src_node_id: srcNodeId,
        dst_ip: effectiveDst,
        protocol,
        payload,
        dst_node_id: dstKind === 'node' ? dstNodeId : null,
      });
      const hopCount = (result.hops_crossed || []).length;
      const verb =
        result.status === 'delivered'
          ? 'delivered'
          : result.status === 'unreachable'
            ? 'unreachable'
            : 'failed';
      toast.success(
        `Message ${verb}`,
        hopCount > 0
          ? `${hopCount} hop${hopCount === 1 ? '' : 's'} crossed`
          : '0 hops crossed',
      );
      onSent?.({ messageId: result.comm_id, hopsCrossed: result.hops_crossed || [] });
      onClose();
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
      const text = typeof msg === 'string' ? msg : (e as Error).message;
      toast.error('Send failed', text);
    } finally {
      setSending(false);
    }
  }

  // ─── render ────────────────────────────────────────────────
  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="trigger-panel-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-bg-overlay animate-fade-in"
        onClick={onClose}
        aria-hidden
      />

      {/* Card */}
      <div className="relative w-full max-w-2xl max-h-[90vh] flex flex-col bg-bg-surface border border-border rounded-lg shadow-lg animate-slide-in">
        {/* Header */}
        <div className="px-5 py-4 border-b border-border flex items-center gap-3 flex-shrink-0">
          <div className="flex-1 min-w-0">
            <div
              id="trigger-panel-title"
              className="text-base font-semibold text-text-primary"
            >
              Send message
            </div>
            <div className="text-2xs text-text-muted mt-0.5">
              Fire a packet from one host to another and watch it cross the network.
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            ×
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* From / To row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* FROM */}
            <div>
              <label className="block text-2xs font-semibold uppercase tracking-wider text-text-secondary mb-1.5">
                From
              </label>
              <select
                className="w-full h-9 px-3 rounded-md bg-bg-surface-2 border border-border text-text-primary text-sm font-mono focus:border-accent focus:outline-none"
                value={srcNodeId}
                onChange={(e) => setSrcNodeId(e.target.value)}
              >
                {settable.length === 0 ? (
                  <option value="">No hosts in this project</option>
                ) : null}
                {settable.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name} ({n.kind})
                  </option>
                ))}
              </select>
            </div>

            {/* TO */}
            <div>
              <label className="block text-2xs font-semibold uppercase tracking-wider text-text-secondary mb-1.5">
                To
              </label>
              <div className="flex gap-2">
                <select
                  className="h-9 px-2 rounded-md bg-bg-surface-2 border border-border text-text-secondary text-xs"
                  value={dstKind}
                  onChange={(e) => setDstKind(e.target.value as 'node' | 'ip')}
                  aria-label="Destination kind"
                >
                  <option value="node">Node</option>
                  <option value="ip">IP</option>
                </select>
                {dstKind === 'node' ? (
                  <select
                    className="flex-1 min-w-0 h-9 px-3 rounded-md bg-bg-surface-2 border border-border text-text-primary text-sm font-mono focus:border-accent focus:outline-none"
                    value={dstNodeId}
                    onChange={(e) => setDstNodeId(e.target.value)}
                  >
                    {settable
                      .filter((n) => n.id !== srcNodeId)
                      .map((n) => {
                        const ip = n.interfaces.find((i) => i.ip_address)?.ip_address;
                        return (
                          <option key={n.id} value={n.id}>
                            {n.name}
                            {ip ? ` — ${ip}` : ''}
                          </option>
                        );
                      })}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="flex-1 min-w-0 h-9 px-3 rounded-md bg-bg-surface-2 border border-border text-text-primary text-sm font-mono focus:border-accent focus:outline-none placeholder:text-text-muted"
                    placeholder="10.30.10.2"
                    value={dstIp}
                    onChange={(e) => setDstIp(e.target.value)}
                  />
                )}
              </div>
              {dstKind === 'ip' && (
                <div className="text-2xs text-text-muted mt-1">
                  Free-form IP. Useful for probing an IP that isn't wired
                  to any node in the canvas.
                </div>
              )}
            </div>
          </div>

          {/* Protocol */}
          <div>
            <label className="block text-2xs font-semibold uppercase tracking-wider text-text-secondary mb-1.5">
              Protocol
            </label>
            <div className="flex gap-2">
              {PROTOCOLS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setProtocol(p)}
                  className={[
                    'h-9 px-4 rounded-md text-sm font-medium border transition-colors duration-fast',
                    protocol === p
                      ? 'bg-accent/15 border-accent/40 text-accent'
                      : 'bg-bg-surface-2 border-border text-text-secondary hover:border-border-strong',
                  ].join(' ')}
                >
                  {p}
                </button>
              ))}
            </div>
            <div className="text-2xs text-text-muted mt-1.5">
              {PROTOCOL_HINT[protocol]}
            </div>
          </div>

          {/* Payload */}
          <div>
            <label className="block text-2xs font-semibold uppercase tracking-wider text-text-secondary mb-1.5">
              Payload
            </label>
            <textarea
              className="w-full h-20 px-3 py-2 rounded-md bg-bg-surface-2 border border-border text-text-primary text-sm font-mono focus:border-accent focus:outline-none resize-none placeholder:text-text-muted"
              placeholder="hello"
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
            />
          </div>

          {/* Route preview */}
          <div>
            <label className="block text-2xs font-semibold uppercase tracking-wider text-text-secondary mb-1.5">
              Route preview
            </label>
            <RoutePreview route={route} />
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-border flex items-center gap-2 flex-shrink-0">
          <div className="flex-1 text-2xs text-text-muted">
            {route.kind === 'ok'
              ? `${route.data.hops.length} hop${route.data.hops.length === 1 ? '' : 's'}`
              : route.kind === 'loading'
                ? 'Resolving…'
                : route.kind === 'unreachable'
                  ? 'Unreachable'
                  : route.kind === 'loop'
                    ? 'Routing loop'
                    : ''}
          </div>
          <Button variant="ghost" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void handleSend()}
            loading={sending}
            disabled={!canSend}
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Route preview ────────────────────────────────────────────────

function RoutePreview({
  route,
}: {
  route:
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'ok'; data: RouteResponse }
    | { kind: 'unreachable'; message: string }
    | { kind: 'loop'; visited: string[] }
    | { kind: 'error'; message: string };
}) {
  if (route.kind === 'idle') {
    return (
      <div className="rounded-md border border-border bg-bg-surface-2 p-4 text-2xs text-text-muted">
        Pick a source and destination to see the route.
      </div>
    );
  }
  if (route.kind === 'loading') {
    return (
      <div className="rounded-md border border-border bg-bg-surface-2 p-4 text-2xs text-text-muted">
        Resolving route…
      </div>
    );
  }
  if (route.kind === 'error') {
    return (
      <div className="rounded-md border border-danger/40 bg-danger-soft p-4 text-2xs text-danger">
        {route.message}
      </div>
    );
  }
  if (route.kind === 'unreachable') {
    return (
      <div className="rounded-md border border-warn/40 bg-warn-soft p-4">
        <div className="text-2xs font-semibold text-warn mb-1">
          Unreachable
        </div>
        <div className="text-2xs text-text-primary">{route.message}</div>
      </div>
    );
  }
  if (route.kind === 'loop') {
    return (
      <div className="rounded-md border border-warn/40 bg-warn-soft p-4">
        <div className="text-2xs font-semibold text-warn mb-1">
          Routing loop detected
        </div>
        <div className="text-2xs text-text-primary font-mono break-all">
          {route.visited.join(' → ')}
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-border bg-bg-surface-2 p-3 space-y-1.5">
      {route.data.hops.map((hop, i) => (
        <HopRow key={i} hop={hop} index={i} />
      ))}
    </div>
  );
}

function HopRow({ hop, index }: { hop: Hop; index: number }) {
  return (
    <div className="flex items-center gap-3 text-2xs">
      <div className="w-5 h-5 rounded-full bg-bg-base border border-border flex items-center justify-center font-mono text-text-muted flex-shrink-0">
        {index}
      </div>
      <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-text-primary">{hop.node_name}</span>
        <NodeKindPill kind={hop.node_kind} />
        {hop.iface_name && (
          <span className="font-mono text-text-secondary">
            {hop.iface_name}
            {hop.iface_ip ? `: ${hop.iface_ip}` : ''}
          </span>
        )}
      </div>
      {hop.link_subnet && (
        <span className="font-mono text-text-muted whitespace-nowrap">
          {hop.link_subnet}
        </span>
      )}
    </div>
  );
}

function NodeKindPill({ kind }: { kind: string }) {
  const validKinds = ['host', 'switch', 'router', 'server', 'attacker'] as const;
  type KindTone = (typeof validKinds)[number] | 'idle';
  const tone: KindTone = (validKinds as readonly string[]).includes(kind)
    ? (kind as KindTone)
    : 'idle';
  return (
    <StatusPill tone={tone} dot>
      {kind}
    </StatusPill>
  );
}
