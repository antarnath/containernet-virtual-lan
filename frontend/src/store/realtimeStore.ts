// realtimeStore — owns the per-project WebSocket connection and the
// list of live anomaly events the user has dismissed.
//
// Why a store instead of a hook in each component?
//   * One WS per project (shared between every panel/listener).
//   * Survives panel close + reopen (the user re-opens the same
//     router and we still have the "still open" events cached).
//   * Survives navigation: the WS reconnects when the user comes
//     back to the canvas page.
//
// The WS protocol (server → client):
//   { type: "anomaly", id, node_id, kind, severity, summary,
//     detail, created_at, resolved_at }
//   { type: "attack_signal", id, attacker_node_id, victim_node_id,
//     signal_kind, value, threshold, window_sec, created_at }
//     ← fires when the backend's attack_detector writes a row.
//   { type: "packet", id, link_id, protocol, src_node_kind, ... }
//     ← broadcast from the per-link packet streamer so the canvas
//       can animate a dot along the wire each time a packet crosses.
//   { type: "message", comm_id, src_node_id, dst_node_id, dst_ip,
//     protocol, payload, status, hops_crossed, delivered_at }
//     ← fired by the backend after every communication_service.send_message
//       so the canvas can highlight the per-link hop trail in real time.
//   { type: "event", id, project_id, ts, kind, summary, detail, ... }
//     ← fires from event_service for lifecycle / node / link / bridge
//       / message / anomaly / attack_signal / error events. This is
//       the same row the LogsView reads.
//   { type: "ping" }   ← heartbeat every 25s (no payload we care about)

import { create } from 'zustand';
import { ProjectsAPI, type AnomalyEvent, type ProjectEventRow } from '../api/client';

export interface RealtimePacketEvent {
  id: number;
  link_id: string;
  protocol: 'tcp' | 'udp' | 'icmp' | 'arp' | 'http' | 'other';
  src_node_kind: string;
  src_ip?: string;
  dst_ip?: string;
  src_port?: number | null;
  dst_port?: number | null;
  ts_ns?: number;
  /** M4 phase 08 — full decoded protocol layers when the
   *  backend includes them (SSE per-link stream always does; WS
   *  broadcasts include them when we have the data). */
  raw?: {
    l2?: Record<string, unknown>;
    l3?: Record<string, unknown> | null;
    l4?: Record<string, unknown> | null;
    l7?: Record<string, unknown> | null;
  };
}

export interface RealtimeAttackSignal {
  id: string;
  attacker_node_id: string;
  victim_node_id?: string | null;
  signal_kind: 'arp_rate' | 'syn_rate' | 'http_rate' | 'new_mac' | 'duplicate_ip';
  value: number;
  threshold: number;
  window_sec: number;
  created_at: string;
}

/** M4 phase 08 — message event broadcast over the project WS
 *  after every send_message. The canvas watches `hops_crossed`
 *  to draw the live "data flowing" trail along each link. */
export interface RealtimeMessageEvent {
  comm_id: string;
  src_node_id: string;
  src_node_name?: string;
  dst_node_id: string | null;
  dst_ip: string;
  protocol: string;
  payload: string;
  status: 'delivered' | 'failed' | 'unreachable';
  hops_crossed: string[]; // link_ids
  delivered_at: string | null;
}

const PACKET_RING_SIZE = 20;
const SIGNAL_RING_SIZE = 50;
const EVENT_RING_SIZE = 200;
const ACTIVE_ATTACKER_TIMEOUT_MS = 10_000;
/** How long a wire glows on the canvas after a message traverses
 *  it (the live "data flowing" effect). The hop_list and comm_id
 *  let the canvas label the glow. */
const MESSAGE_TRAIL_MS = 2_500;
type PacketRing = Map<string, RealtimePacketEvent[]>;
type AttackSignalsByAttacker = Map<string, RealtimeAttackSignal[]>;

/** M4 phase 08 — one in-flight message hop trail. Each link the
 *  message crossed has its own expiry so the canvas can fade
 *  them in sequence. */
export interface MessageTrail {
  comm_id: string;
  src_node_id: string;
  dst_node_id: string | null;
  dst_ip: string;
  protocol: string;
  /** link_id → expiry timestamp (ms epoch) */
  link_expiries: Map<string, number>;
}

interface RealtimeState {
  /** Current project (null when not on a project page). */
  projectId: string | null;
  /** Live anomaly events, newest first. */
  anomalies: AnomalyEvent[];
  /** Live attack signals, newest first, bucketed per attacker. */
  attackSignals: AttackSignalsByAttacker;
  /** Attacker IDs that have produced at least one signal in the last
   *  ACTIVE_ATTACKER_TIMEOUT_MS — drives the canvas red ring. */
  activeAttackers: Set<string>;
  /** Project events (the unified timeline). Newest first. Capped at
   *  EVENT_RING_SIZE to keep memory bounded. */
  events: ProjectEventRow[];
  /** WS connection state. */
  wsState: 'idle' | 'connecting' | 'open' | 'closed';
  /** IDs the user has dismissed (locally). We strip them out of the
   * banner list so a flapping event doesn't pop back in. The server
   *  also marks the row resolved (POST /anomalies/{id}/dismiss). */
  dismissedIds: Set<string>;
  /** Most recent N packets per link (newest last), for the canvas
   *  dot animation. Cleared on disconnect. */
  packetsByLink: PacketRing;
  /** M4 phase 08 — most recent message trails, keyed by comm_id.
   *  A canvas wire whose id is in any trail's `link_expiries`
   *  (with expiry in the future) should glow to indicate the
   *  message is flowing across it. */
  messageTrails: Map<string, MessageTrail>;

  // ─── lifecycle ──────────────────────────────────────────────
  connect: (projectId: string) => void;
  disconnect: () => void;
  dismissAnomaly: (id: string) => Promise<void>;

  // ─── test seam ──────────────────────────────────────────────
  _ingestTestEvent: (ev: AnomalyEvent) => void;
  _ingestPacket: (ev: RealtimePacketEvent) => void;
  _ingestAttackSignal: (ev: RealtimeAttackSignal) => void;
  _ingestEvent: (ev: ProjectEventRow) => void;
  _ingestMessage: (ev: RealtimeMessageEvent) => void;
  pruneActiveAttackers: () => void;
  /** Drop expired link_expiries from every trail. Called by the
   *  canvas on a 250ms timer. */
  pruneMessageTrails: () => void;
}

let ws: WebSocket | null = null;
let reconnectTimer: number | null = null;

function wsUrlFor(_projectId: string): string {
  // M4 phase 03 — single global WS at /api/ws. The client subscribes
  // to a project by sending `{type: "subscribe", project_id}` after
  // onopen (see backend/app/api/websocket.py). The path doesn't carry
  // the project id.
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/ws`;
}

function scheduleReconnect(projectId: string) {
  if (reconnectTimer) return;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    openSocket(projectId);
  }, 3000);
}

function openSocket(projectId: string) {
  // Drop any previous socket before opening a new one.
  if (ws) {
    try { ws.close(); } catch { /* noop */ }
    ws = null;
  }
  useRealtimeStore.setState({ wsState: 'connecting' });
  let socket: WebSocket;
  try {
    socket = new WebSocket(wsUrlFor(projectId));
  } catch {
    useRealtimeStore.setState({ wsState: 'closed' });
    scheduleReconnect(projectId);
    return;
  }
  ws = socket;
  socket.onopen = () => {
    useRealtimeStore.setState({ wsState: 'open' });
    // The backend (/ws) routes project-scoped events only to sockets
    // that have explicitly subscribed (see backend/app/api/websocket.py).
    // The subscribe envelope must be sent right after onopen — without
    // it, the server will never deliver anomaly / attack_signal /
    // message / event broadcasts to this client.
    try {
      socket.send(JSON.stringify({ type: 'subscribe', project_id: projectId }));
    } catch {
      // Best-effort: onclose will fire and we'll reconnect.
    }
  };
  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (!msg || typeof msg !== 'object') return;
      // The server publishes events wrapped in a standard envelope
      // (see app/ws/events.py): {type, project_id, data, ts}. The
      // domain event lives in `data` (with its own `type` field),
      // so we unwrap before dispatching to the typed handlers.
      const inner = (msg.data && typeof msg.data === 'object' && msg.data.type)
        ? msg.data
        : msg;
      if (inner.type === 'anomaly') {
        useRealtimeStore.getState()._ingestTestEvent(inner as AnomalyEvent);
      } else if (inner.type === 'packet') {
        useRealtimeStore.getState()._ingestPacket(inner as RealtimePacketEvent);
      } else if (inner.type === 'attack_signal') {
        useRealtimeStore.getState()._ingestAttackSignal(inner as RealtimeAttackSignal);
      } else if (inner.type === 'event') {
        useRealtimeStore.getState()._ingestEvent(inner as ProjectEventRow);
      } else if (inner.type === 'message') {
        useRealtimeStore.getState()._ingestMessage(inner as RealtimeMessageEvent);
      }
    } catch {
      // ignore malformed
    }
  };
  socket.onerror = () => {
    // Browser will fire onclose right after; reconnect logic lives there.
  };
  socket.onclose = () => {
    ws = null;
    useRealtimeStore.setState({ wsState: 'closed' });
    // If we're still on this project, retry.
    if (useRealtimeStore.getState().projectId === projectId) {
      scheduleReconnect(projectId);
    }
  };
}

export const useRealtimeStore = create<RealtimeState>((set, get) => ({
  projectId: null,
  anomalies: [],
  attackSignals: new Map(),
  activeAttackers: new Set(),
  events: [],
  wsState: 'idle',
  dismissedIds: new Set(),
  packetsByLink: new Map(),
  messageTrails: new Map(),

  connect: (projectId) => {
    const prev = get().projectId;
    if (prev === projectId && ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    set({
      projectId,
      anomalies: [],
      attackSignals: new Map(),
      activeAttackers: new Set(),
      events: [],
      dismissedIds: new Set(),
      packetsByLink: new Map(),
      messageTrails: new Map(),
    });
    // Pull a fresh snapshot from the REST endpoint so the UI has the
    // full history on connect, not just whatever the WS happens to
    // deliver next.
    void ProjectsAPI.anomalies.list(projectId, true).then((res) => {
      // Only apply if we're still on this project (user may have
      // navigated away while the request was in flight).
      if (get().projectId !== projectId) return;
      set((s) => ({
        anomalies: mergeAnomalies(s.anomalies, res.anomalies || []),
      }));
    }).catch(() => {
      // ignore — polling endpoints still work
    });
    // Same idea for the event timeline — backfill on connect.
    void ProjectsAPI.events.list(projectId, { limit: 100 }).then((res) => {
      if (get().projectId !== projectId) return;
      set({ events: res.events || [] });
    }).catch(() => {
      // ignore
    });
    openSocket(projectId);
  },

  disconnect: () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      try { ws.close(); } catch { /* noop */ }
      ws = null;
    }
    set({
      projectId: null,
      anomalies: [],
      attackSignals: new Map(),
      activeAttackers: new Set(),
      events: [],
      wsState: 'idle',
      packetsByLink: new Map(),
      messageTrails: new Map(),
    });
  },

  dismissAnomaly: async (id) => {
    const projectId = get().projectId;
    if (!projectId) return;
    set((s) => {
      const next = new Set(s.dismissedIds);
      next.add(id);
      return { dismissedIds: next };
    });
    try {
      await ProjectsAPI.anomalies.dismiss(projectId, id);
      set((s) => ({
        anomalies: s.anomalies.map((a) =>
          a.id === id ? { ...a, resolved_at: new Date().toISOString() } : a,
        ),
      }));
    } catch {
      // Best-effort: the optimistic local state already hides the
      // banner. Real retry happens on the next REST snapshot.
    }
  },

  _ingestTestEvent: (ev) => {
    set((s) => {
      // Dedup by id.
      if (s.anomalies.some((a) => a.id === ev.id)) return s;
      return { anomalies: [ev, ...s.anomalies] };
    });
  },

  _ingestPacket: (ev) => {
    if (!ev || !ev.link_id) return;
    set((s) => {
      const next = new Map(s.packetsByLink);
      const bucket = next.get(ev.link_id) ?? [];
      const updated = bucket.concat(ev);
      if (updated.length > PACKET_RING_SIZE) {
        updated.splice(0, updated.length - PACKET_RING_SIZE);
      }
      next.set(ev.link_id, updated);
      return { packetsByLink: next };
    });
  },

  _ingestAttackSignal: (ev) => {
    if (!ev || !ev.id || !ev.attacker_node_id) return;
    set((s) => {
      const next = new Map(s.attackSignals);
      const bucket = next.get(ev.attacker_node_id) ?? [];
      // Dedup by id (WS may race the REST snapshot).
      if (bucket.some((x) => x.id === ev.id)) return s;
      const updated = [ev, ...bucket].slice(0, SIGNAL_RING_SIZE);
      next.set(ev.attacker_node_id, updated);
      const active = new Set(s.activeAttackers);
      active.add(ev.attacker_node_id);
      return { attackSignals: next, activeAttackers: active };
    });
  },

  _ingestEvent: (ev) => {
    if (!ev || !ev.id) return;
    set((s) => {
      if (s.events.some((e) => e.id === ev.id)) return s;
      const next = [ev, ...s.events].slice(0, EVENT_RING_SIZE);
      return { events: next };
    });
  },

  _ingestMessage: (ev) => {
    if (!ev || !ev.comm_id) return;
    // Build a per-link expiry map. Each link the message crossed
    // gets a 2.5s glow so the user can see the data flowing.
    const link_expiries = new Map<string, number>();
    const expires = Date.now() + MESSAGE_TRAIL_MS;
    for (const lid of ev.hops_crossed || []) {
      link_expiries.set(lid, expires);
    }
    const trail: MessageTrail = {
      comm_id: ev.comm_id,
      src_node_id: ev.src_node_id,
      dst_node_id: ev.dst_node_id,
      dst_ip: ev.dst_ip,
      protocol: ev.protocol,
      link_expiries,
    };
    set((s) => {
      const next = new Map(s.messageTrails);
      next.set(ev.comm_id, trail);
      // Cap the trail buffer at 8 most-recent to keep memory bounded.
      if (next.size > 8) {
        const first = next.keys().next().value;
        if (first !== undefined) next.delete(first);
      }
      return { messageTrails: next };
    });
  },

  pruneMessageTrails: () => {
    const now = Date.now();
    set((s) => {
      let mutated = false;
      const next = new Map(s.messageTrails);
      for (const [commId, trail] of next.entries()) {
        let stillActive = false;
        for (const exp of trail.link_expiries.values()) {
          if (exp > now) {
            stillActive = true;
            break;
          }
        }
        if (!stillActive) {
          next.delete(commId);
          mutated = true;
        }
      }
      return mutated ? { messageTrails: next } : s;
    });
  },

  pruneActiveAttackers: () => {
    // Called periodically by the UI; we keep attackers "active" for
    // ACTIVE_ATTACKER_TIMEOUT_MS after their last signal. The actual
    // timestamps are tracked in the signal list; this is a coarse
    // sweep that clears attackers whose most recent signal is older
    // than the timeout.
    const cutoff = Date.now() - ACTIVE_ATTACKER_TIMEOUT_MS;
    set((s) => {
      let mutated = false;
      const active = new Set(s.activeAttackers);
      for (const id of active) {
        const bucket = s.attackSignals.get(id);
        if (!bucket || bucket.length === 0) {
          active.delete(id);
          mutated = true;
          continue;
        }
        const last = bucket[0]?.created_at;
        if (!last) continue;
        const t = new Date(last).getTime();
        if (t < cutoff) {
          active.delete(id);
          mutated = true;
        }
      }
      return mutated ? { activeAttackers: active } : s;
    });
  },
}));

function mergeAnomalies(prev: AnomalyEvent[], next: AnomalyEvent[]): AnomalyEvent[] {
  const byId = new Map<string, AnomalyEvent>();
  for (const n of next) byId.set(n.id, n);
  for (const p of prev) {
    if (!byId.has(p.id)) byId.set(p.id, p);
  }
  return Array.from(byId.values()).sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
    return tb - ta;
  });
}
