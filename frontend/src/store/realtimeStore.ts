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
//   { type: "packet", id, link_id, protocol, src_node_kind, ... }
//     ← broadcast from the per-link packet streamer so the canvas
//       can animate a dot along the wire each time a packet crosses.
//   { type: "ping" }   ← heartbeat every 25s (no payload we care about)

import { create } from 'zustand';
import { ProjectsAPI, type AnomalyEvent } from '../api/client';

export interface RealtimePacketEvent {
  id: number;
  link_id: string;
  protocol: 'tcp' | 'udp' | 'icmp' | 'arp' | 'http' | 'other';
  src_node_kind: string;
  src_ip?: string;
  dst_ip?: string;
  ts_ns?: number;
}

const PACKET_RING_SIZE = 20;
type PacketRing = Map<string, RealtimePacketEvent[]>;

interface RealtimeState {
  /** Current project (null when not on a project page). */
  projectId: string | null;
  /** Live anomaly events, newest first. */
  anomalies: AnomalyEvent[];
  /** WS connection state. */
  wsState: 'idle' | 'connecting' | 'open' | 'closed';
  /** IDs the user has dismissed (locally). We strip them out of the
   * banner list so a flapping event doesn't pop back in. The server
   *  also marks the row resolved (POST /anomalies/{id}/dismiss). */
  dismissedIds: Set<string>;
  /** Most recent N packets per link (newest last), for the canvas
   *  dot animation. Cleared on disconnect. */
  packetsByLink: PacketRing;

  // ─── lifecycle ──────────────────────────────────────────────
  connect: (projectId: string) => void;
  disconnect: () => void;
  dismissAnomaly: (id: string) => Promise<void>;

  // ─── test seam ──────────────────────────────────────────────
  _ingestTestEvent: (ev: AnomalyEvent) => void;
  _ingestPacket: (ev: RealtimePacketEvent) => void;
}

let ws: WebSocket | null = null;
let reconnectTimer: number | null = null;

function wsUrlFor(projectId: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/ws/projects/${projectId}`;
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
  };
  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'anomaly') {
        useRealtimeStore.getState()._ingestTestEvent(msg as AnomalyEvent);
      } else if (msg.type === 'packet') {
        useRealtimeStore.getState()._ingestPacket(msg as RealtimePacketEvent);
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
  wsState: 'idle',
  dismissedIds: new Set(),
  packetsByLink: new Map(),

  connect: (projectId) => {
    const prev = get().projectId;
    if (prev === projectId && ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    set({
      projectId,
      anomalies: [],
      dismissedIds: new Set(),
      packetsByLink: new Map(),
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
    set({ projectId: null, anomalies: [], wsState: 'idle', packetsByLink: new Map() });
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
